"""AI meal analysis: photo and/or text in, structured macro estimate out."""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from ..db import get_connection
from ..schemas import AnalysisLink, MealAnalysis, MealAnalysisResponse
from ..services import meal_ai

router = APIRouter(prefix="/api/ai", tags=["ai"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/analyze", response_model=MealAnalysisResponse)
async def analyze(
    image: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    prior_analysis: str | None = Form(default=None),
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

    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO ai_analyses (user_text, analysis_json) VALUES (?, ?)",
            (text, analysis.model_dump_json()),
        )
        conn.commit()
        analysis_id = cur.lastrowid
    finally:
        conn.close()

    return MealAnalysisResponse(**analysis.model_dump(), analysis_id=analysis_id)


@router.patch("/analyses/{analysis_id}", status_code=204)
def link_analysis(analysis_id: int, link: AnalysisLink):
    """Attach the saved meal's id to an analysis (best-effort, from the client)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE ai_analyses SET meal_id = ? WHERE id = ?",
            (link.meal_id, analysis_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Analysis not found")
    finally:
        conn.close()
