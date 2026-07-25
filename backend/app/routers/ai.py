"""AI meal analysis: photo and/or text in, structured macro estimate out."""
import os
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import AIAnalysis, Meal, User
from ..schemas import AnalysisLink, MealAnalysis, MealAnalysisResponse
from ..services import meal_ai

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
DEFAULT_DAILY_LIMIT = 20

# Provider failures the user can act on get their own status and wording. The
# provider's actual message stays in the logs (services/meal_ai.py logs it)
# instead of going to the client.
_PROVIDER_ERRORS: list[tuple[type, int, str]] = [
    (
        meal_ai.MealAIRateLimited,
        429,
        "The AI service is busy right now. Try again in a minute, or enter macros manually.",
    ),
    (
        meal_ai.MealAIUnavailable,
        503,
        "The AI service is temporarily unavailable. Try again shortly, or enter macros manually.",
    ),
    (
        meal_ai.MealAIBadResponse,
        502,
        "The AI returned an unreadable estimate. Try again, or enter macros manually.",
    ),
    (
        meal_ai.MealAIBadRequest,
        502,
        "AI analysis is misconfigured on the server — check the server logs.",
    ),
]


def _daily_limit() -> int:
    return int(os.environ.get("AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))


def _provider_http_error(exc: Exception) -> HTTPException:
    for kind, status, detail in _PROVIDER_ERRORS:
        if isinstance(exc, kind):
            return HTTPException(status_code=status, detail=detail)
    return HTTPException(
        status_code=502,
        detail="AI analysis failed. Try again or enter macros manually.",
    )


async def _read_media(
    upload: UploadFile, kind: str, max_bytes: int, a_noun: str, noun: str
) -> tuple[bytes, str | None]:
    """Validate one uploaded media file and return its bytes plus mime type."""
    if upload.content_type and not upload.content_type.startswith(f"{kind}/"):
        raise HTTPException(status_code=415, detail=f"File must be {a_noun}.")
    data = await upload.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{noun} too large (max {max_bytes // (1024 * 1024)} MB).",
        )
    return data, upload.content_type


def _analyses_today(db: Session, user_id: int) -> int:
    # created_at is stored as naive UTC; compute the day boundary in Python so
    # SQLite and Postgres behave identically.
    utc_midnight = datetime.combine(
        datetime.now(timezone.utc).date(), time.min
    )
    return db.scalar(
        select(func.count())
        .select_from(AIAnalysis)
        .where(AIAnalysis.user_id == user_id, AIAnalysis.created_at >= utc_midnight)
    )


@router.post("/analyze", response_model=MealAnalysisResponse)
async def analyze(
    image: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
    # Length caps bound what can be relayed to the paid Gemini API.
    text: str | None = Form(default=None, max_length=2_000),
    prior_analysis: str | None = Form(default=None, max_length=20_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = (text or "").strip() or None
    if image is None and audio is None and text is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a photo, a voice note, or a description.",
        )
    if not meal_ai.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI analysis is not configured on the server (GEMINI_API_KEY).",
        )

    prior: MealAnalysis | None = None
    if prior_analysis:
        try:
            prior = MealAnalysis.model_validate_json(prior_analysis)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Invalid prior_analysis.")

    image_bytes = image_mime = None
    if image is not None:
        image_bytes, image_mime = await _read_media(
            image, "image", MAX_IMAGE_BYTES, "an image", "Image"
        )

    audio_bytes = audio_mime = None
    if audio is not None:
        audio_bytes, audio_mime = await _read_media(
            audio, "audio", MAX_AUDIO_BYTES, "audio", "Audio"
        )

    # Reserve a quota slot *before* the slow provider call: lock the user row
    # (a no-op on SQLite, which serializes writes anyway) so concurrent
    # requests can't both pass the count check, then commit the reservation.
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    limit = _daily_limit()
    if _analyses_today(db, user.id) >= limit:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily AI analysis limit reached ({limit}/day). "
                "Try again tomorrow or enter macros manually."
            ),
        )
    record = AIAnalysis(user_id=user.id, user_text=text, analysis_json="")
    db.add(record)
    db.commit()

    try:
        analysis = await meal_ai.analyze_meal(
            image_bytes, image_mime, text, prior,
            audio_bytes=audio_bytes, audio_mime=audio_mime,
        )
    except Exception as exc:
        # Refund the reserved slot — a provider failure shouldn't count
        # against the user's daily limit.
        db.delete(record)
        db.commit()
        raise _provider_http_error(exc)

    record.analysis_json = analysis.model_dump_json()
    db.commit()

    return MealAnalysisResponse(**analysis.model_dump(), analysis_id=record.id)


@router.patch("/analyses/{analysis_id}", status_code=204)
def link_analysis(
    analysis_id: int,
    link: AnalysisLink,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach the saved meal's id to an analysis (best-effort, from the client)."""
    record = db.scalars(
        select(AIAnalysis).where(
            AIAnalysis.id == analysis_id, AIAnalysis.user_id == user.id
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    # The target meal must also belong to the caller, or users could attach
    # analyses to other people's meals.
    meal = db.scalars(
        select(Meal.id).where(Meal.id == link.meal_id, Meal.user_id == user.id)
    ).first()
    if meal is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    record.meal_id = link.meal_id
    db.commit()
