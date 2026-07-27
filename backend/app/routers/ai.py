"""AI meal analysis: photo and/or text in, structured macro estimate out."""
import logging
import os
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import AIAnalysis, Meal, User
from ..schemas import (
    AnalysisLink,
    MealAnalysis,
    MealAnalysisResponse,
    TranscriptionResponse,
)
from ..services import meal_ai

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
DEFAULT_DAILY_LIMIT = 20
# Transcription is a cheaper call than analysis and a voice note usually
# precedes one, so it gets its own allowance rather than eating the analysis
# budget — otherwise speaking your meal would cost twice as much as typing it.
DEFAULT_TRANSCRIBE_DAILY_LIMIT = 40
# Ceiling across ALL users and both kinds of call. The per-user limits bound
# one account; nothing bounded the total, so signing up repeatedly could drain
# the shared provider quota (or, on a paid key, run up a bill). Sized well
# above legitimate use and well below the free tier's ~1500/day.
DEFAULT_GLOBAL_DAILY_LIMIT = 500

KIND_ANALYSIS = "analysis"
KIND_TRANSCRIPTION = "transcription"

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


def _transcribe_daily_limit() -> int:
    return int(
        os.environ.get("AI_TRANSCRIBE_DAILY_LIMIT", DEFAULT_TRANSCRIBE_DAILY_LIMIT)
    )


def _global_daily_limit() -> int:
    return int(os.environ.get("AI_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT))


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
    """Validate one uploaded media file and return its bytes plus mime type.

    The browser's content type is forwarded verbatim, parameters included.
    MediaRecorder sends `audio/webm;codecs=opus` and Gemini accepts it — that
    is the form running in production. Stripping the codecs parameter would
    substitute a value never tested against the live provider.
    """
    if upload.content_type and not upload.content_type.startswith(f"{kind}/"):
        raise HTTPException(status_code=415, detail=f"File must be {a_noun}.")
    data = await upload.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{noun} too large (max {max_bytes // (1024 * 1024)} MB).",
        )
    return data, upload.content_type


def _calls_today(
    db: Session, *, user_id: int | None = None, kind: str | None = None
) -> int:
    """Provider calls made since UTC midnight, optionally narrowed.

    Every ai_analyses row is one billable call, so counting rows is the quota.
    created_at is stored as naive UTC; the day boundary is computed in Python
    so SQLite and Postgres behave identically.
    """
    utc_midnight = datetime.combine(datetime.now(timezone.utc).date(), time.min)
    query = (
        select(func.count())
        .select_from(AIAnalysis)
        .where(AIAnalysis.created_at >= utc_midnight)
    )
    if user_id is not None:
        query = query.where(AIAnalysis.user_id == user_id)
    if kind is not None:
        query = query.where(AIAnalysis.kind == kind)
    return db.scalar(query)


def _reserve_call(
    db: Session,
    user: User,
    *,
    kind: str,
    per_user_limit: int,
    noun: str,
    user_text: str | None = None,
) -> AIAnalysis:
    """Claim one provider call for this user, or raise 429/503.

    Reserved *before* the slow provider call rather than counted after: the
    user row is locked (a no-op on SQLite, which serializes writes anyway) so
    two concurrent requests can't both pass the check. Callers must delete the
    returned row if the provider call fails, so an outage costs the user
    nothing.

    The global check is deliberately not locked — serializing every AI request
    across all users to make a coarse ceiling exact would cost more than the
    handful of calls a race could let through.
    """
    db.execute(select(User.id).where(User.id == user.id).with_for_update())

    if _calls_today(db, user_id=user.id, kind=kind) >= per_user_limit:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily {noun} limit reached ({per_user_limit}/day). "
                "Try again tomorrow or enter macros manually."
            ),
        )

    global_limit = _global_daily_limit()
    if _calls_today(db) >= global_limit:
        db.rollback()
        logger.warning(
            "Global daily AI cap reached (%s/day); rejecting %s for user %s",
            global_limit, kind, user.id,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "The app's shared daily AI quota is used up. "
                "Try again tomorrow, or enter macros manually."
            ),
        )

    record = AIAnalysis(
        user_id=user.id, user_text=user_text, analysis_json="", kind=kind
    )
    db.add(record)
    db.commit()
    return record


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

    record = _reserve_call(
        db,
        user,
        kind=KIND_ANALYSIS,
        per_user_limit=_daily_limit(),
        noun="AI analysis",
        user_text=text,
    )

    try:
        analysis = await meal_ai.analyze_meal(
            image_bytes, image_mime, text, prior,
            audio_bytes=audio_bytes, audio_mime=audio_mime,
        )
    except meal_ai.MealAIBadResponse as exc:
        # The model ran and burned tokens; only its output was unusable, so the
        # slot stays spent. Refunding here would make "send input that reliably
        # produces garbage" an uncapped free path to the provider.
        raise _provider_http_error(exc)
    except Exception as exc:
        # Refused (4xx) or unreachable (5xx) — rejected before inference, so
        # nothing was billed and a provider failure shouldn't cost the user a
        # slot.
        db.delete(record)
        db.commit()
        raise _provider_http_error(exc)

    record.analysis_json = analysis.model_dump_json()
    db.commit()

    return MealAnalysisResponse(**analysis.model_dump(), analysis_id=record.id)


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Voice note in, editable text out.

    Separate from /analyze so the user reviews what was heard before it becomes
    an estimate — a misheard ingredient is then a typo to fix, not a wrong
    number to spot afterwards.
    """
    if not meal_ai.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI analysis is not configured on the server (GEMINI_API_KEY).",
        )

    audio_bytes, audio_mime = await _read_media(
        audio, "audio", MAX_AUDIO_BYTES, "audio", "Audio"
    )

    record = _reserve_call(
        db,
        user,
        kind=KIND_TRANSCRIPTION,
        per_user_limit=_transcribe_daily_limit(),
        noun="voice note",
    )

    try:
        transcript = await meal_ai.transcribe_audio(audio_bytes, audio_mime)
    except meal_ai.MealAIBadResponse as exc:
        # Silence, or speech the model couldn't make out. It listened either
        # way, so the slot stays spent — otherwise uploading silence on a loop
        # would be an unmetered way to keep calling the provider.
        raise HTTPException(
            status_code=422,
            detail=(
                "No speech was recognised in that recording. "
                "Try again, or type your description instead."
            ),
        ) from exc
    except Exception as exc:
        # Rejected or unreachable before inference — nothing billed, so refund.
        db.delete(record)
        db.commit()
        raise _provider_http_error(exc)

    # Kept for the same reason analyses are: a record of what the user actually
    # said, to compare against the estimate it produced. The audio is discarded.
    record.user_text = transcript
    db.commit()

    return TranscriptionResponse(transcript=transcript)


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
