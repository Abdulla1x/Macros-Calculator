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
DEFAULT_DAILY_LIMIT = 20


def _daily_limit() -> int:
    return int(os.environ.get("AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))


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
    text: str | None = Form(default=None),
    prior_analysis: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = (text or "").strip() or None
    if image is None and text is None:
        raise HTTPException(
            status_code=422, detail="Provide a photo, a description, or both."
        )
    if not meal_ai.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI analysis is not configured on the server (GEMINI_API_KEY).",
        )

    limit = _daily_limit()
    if _analyses_today(db, user.id) >= limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily AI analysis limit reached ({limit}/day). "
                "Try again tomorrow or enter macros manually."
            ),
        )

    prior: MealAnalysis | None = None
    if prior_analysis:
        try:
            prior = MealAnalysis.model_validate_json(prior_analysis)
        except ValidationError:
            raise HTTPException(status_code=422, detail="Invalid prior_analysis.")

    image_bytes = image_mime = None
    if image is not None:
        if image.content_type and not image.content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="File must be an image.")
        image_bytes = await image.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image too large (max 5 MB).")
        image_mime = image.content_type

    try:
        analysis = await meal_ai.analyze_meal(image_bytes, image_mime, text, prior)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="AI analysis failed. Try again or enter macros manually.",
        )

    record = AIAnalysis(
        user_id=user.id, user_text=text, analysis_json=analysis.model_dump_json()
    )
    db.add(record)
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
