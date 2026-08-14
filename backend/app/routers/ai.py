"""AI meal analysis: photo and/or text in, structured macro estimate out."""
import logging
import os
import time as time_module
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import AIAnalysis, Meal, User
from ..schemas import (
    AIProbe,
    AIStatus,
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
# Several angles of one meal (or the packet's nutrition label alongside the
# plate) genuinely sharpen an estimate, but each image is billed as input
# tokens, and the quota counts *calls* — four photos is still one ai_analyses
# row, so nothing else in this file bounds what one request can cost. This
# constant is that bound. Raising it raises the per-analysis token bill
# proportionally.
MAX_IMAGES = 4
# A separate ceiling from MAX_IMAGES * MAX_IMAGE_BYTES (20 MB): the per-image
# limit exists to reject one absurd file, this one exists so a single request
# can't tie up a free-tier instance's memory holding every upload at once.
MAX_TOTAL_IMAGE_BYTES = 12 * 1024 * 1024
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
KIND_PROBE = "probe"

DEFAULT_PROBE_DAILY_LIMIT = 10
STATUS_DETAIL_ENV = "MEAL_AI_STATUS_DETAIL"

# One shared probe result for the whole process. Render runs a single free
# instance, so a module-level cache is a real cache — and it is what stops a
# diagnostic endpoint becoming an unmetered path to the provider: however many
# people ask, however often, Google is asked at most once a minute.
PROBE_TTL_SECONDS = 60
_probe_cache: tuple[float, AIProbe] | None = None

# Neutral exception -> probe classification. Same shape and same reason as
# _PROVIDER_ERRORS: the router names outcomes, meal_ai.py owns which provider
# failure becomes which exception.
_PROBE_STATUS: list[tuple[type, str]] = [
    (meal_ai.MealAIRateLimited, "rate_limited"),
    (meal_ai.MealAIUnavailable, "upstream_5xx"),
    (meal_ai.MealAIUnreachable, "unreachable"),
    (meal_ai.MealAIInternalError, "internal_error"),
    (meal_ai.MealAIBadRequest, "rejected"),
    (meal_ai.MealAIBadResponse, "rejected"),
]

# "Google returned 5xx", "we could not reach Google" and "our SDK raised" get
# identical wording on purpose: they reduce to the same instruction for a user,
# and splitting them would leak an operational distinction nobody outside the
# server can act on. The distinction lives in the logs and in GET /api/ai/status.
_UNAVAILABLE_DETAIL = (
    "The AI service is temporarily unavailable. Try again shortly, "
    "or enter macros manually."
)

# Provider failures the user can act on get their own status and wording. The
# provider's actual message stays in the logs (services/meal_ai.py logs it)
# instead of going to the client.
_PROVIDER_ERRORS: list[tuple[type, int, str]] = [
    (
        meal_ai.MealAIRateLimited,
        429,
        "The AI service is busy right now. Try again in a minute, or enter macros manually.",
    ),
    (meal_ai.MealAIUnavailable, 503, _UNAVAILABLE_DETAIL),
    (meal_ai.MealAIUnreachable, 503, _UNAVAILABLE_DETAIL),
    # The residual bucket keeps the user-facing 503 rather than the operator's
    # 502: these are the failures we did not anticipate, and the safe default
    # for an unknown one is not telling someone their app is permanently broken
    # when it might not be. The operator gets the truth from the log line and
    # /api/ai/status, neither of which the user reads.
    (meal_ai.MealAIInternalError, 503, _UNAVAILABLE_DETAIL),
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


def global_daily_limit() -> int:
    return int(os.environ.get("AI_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT))


def _probe_daily_limit() -> int:
    return int(os.environ.get("AI_PROBE_DAILY_LIMIT", DEFAULT_PROBE_DAILY_LIMIT))


def _probe_message(exc: Exception) -> str | None:
    """The provider's own words, truncated — the one place they leave the process.

    Off unless MEAL_AI_STATUS_DETAIL is set, so the default deployment leaks
    nothing: signup is open, which makes "authenticated" a weak gate on its own.
    Flipping it in the dashboard during an incident is the same no-deploy escape
    hatch MEAL_AI_MODEL and STATUS_BANNER already use, and it goes back off
    afterwards.
    """
    if not os.environ.get(STATUS_DETAIL_ENV, "").strip():
        return None
    return str(exc)[:300]


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


def calls_today(
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

    if calls_today(db, user_id=user.id, kind=kind) >= per_user_limit:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily {noun} limit reached ({per_user_limit}/day). "
                "Try again tomorrow or enter macros manually."
            ),
        )

    global_limit = global_daily_limit()
    if calls_today(db) >= global_limit:
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


@router.get("/status", response_model=AIStatus)
async def ai_status(
    probe: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Is the AI down, and why — in one request.

    Authenticated because the probe spends a real provider call. `probe` is
    opt-in so the free form (configured, models, SDK version) can be polled or
    scripted without touching Google at all — and because those three facts
    already separate "the key was removed from the dashboard" from everything
    else.
    """
    global _probe_cache
    base = {"configured": meal_ai.is_configured(), **meal_ai.provider_info()}

    if not probe:
        return AIStatus(**base)
    if not base["configured"]:
        return AIStatus(**base, probe=AIProbe(status="not_configured"))

    if _probe_cache is not None:
        age = time_module.monotonic() - _probe_cache[0]
        if age < PROBE_TTL_SECONDS:
            cached = _probe_cache[1].model_copy(
                update={"cached": True, "age_seconds": int(age)}
            )
            return AIStatus(**base, probe=cached)

    try:
        # Reserved like any other provider call: a probe really does spend the
        # shared quota, so hiding it from AI_GLOBAL_DAILY_LIMIT would make that
        # ceiling a lie. Its own `kind` keeps it out of the analysis and
        # voice-note allowances, which calls_today counts per kind.
        _reserve_call(
            db,
            user,
            kind=KIND_PROBE,
            per_user_limit=_probe_daily_limit(),
            noun="AI status probe",
        )
    except HTTPException as exc:
        # A diagnostic that 429s is a diagnostic you cannot use during the
        # incident it was built for, so the cap is reported as an outcome rather
        # than raised. exc.detail is our own wording, never the provider's.
        return AIStatus(
            **base, probe=AIProbe(status="quota_exhausted", message=str(exc.detail))
        )

    started = time_module.monotonic()
    try:
        await meal_ai.probe()
        outcome = AIProbe(status="ok")
    except Exception as exc:
        status = next(
            (s for kind, s in _PROBE_STATUS if isinstance(exc, kind)), "internal_error"
        )
        outcome = AIProbe(status=status, message=_probe_message(exc))
    outcome.latency_ms = int((time_module.monotonic() - started) * 1000)

    # The row is deliberately NOT refunded on failure, unlike /analyze. There a
    # refund protects a user whose meal the provider dropped; here it would make
    # probing free exactly when the provider is failing — which is when this
    # endpoint gets hammered.
    _probe_cache = (time_module.monotonic(), outcome)
    return AIStatus(**base, probe=outcome)


@router.post("/analyze", response_model=MealAnalysisResponse)
async def analyze(
    # Repeated `image` parts, not `images`: the field name is unchanged from
    # when this took exactly one, so a client that still sends a single image
    # keeps working. FastAPI collects the repeats into the list either way.
    #
    # `| str` is not decoration. A file input submitted with nothing selected
    # sends a part with an empty filename, which FastAPI parses as a plain
    # string — and `list[UploadFile]` alone rejects the whole request at
    # validation, before any handler code runs. The result would be a perfectly
    # good text-only analysis refused with an opaque 422. Accept both shapes
    # here and discard the empties below.
    image: list[UploadFile | str] = File(default=[]),
    audio: UploadFile | None = File(default=None),
    # Length caps bound what can be relayed to the paid Gemini API.
    text: str | None = Form(default=None, max_length=2_000),
    prior_analysis: str | None = Form(default=None, max_length=20_000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text = (text or "").strip() or None
    # Drop the empty parts described above, so a browser quirk can't make a
    # text-only request look like it carried a photo.
    # Tested against `str`, not `UploadFile`: under the union annotation the
    # value that arrives is Starlette's UploadFile, and fastapi.UploadFile is a
    # *subclass* of it — so an isinstance check against the imported name is
    # False for every real upload. The empty case is the string one.
    images = [
        item for item in image if not isinstance(item, str) and item.filename
    ]
    if not images and audio is None and text is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a photo, a voice note, or a description.",
        )
    if len(images) > MAX_IMAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Too many photos (max {MAX_IMAGES} per analysis).",
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

    loaded_images: list[tuple[bytes, str | None]] = []
    total_image_bytes = 0
    for upload in images:
        data, mime = await _read_media(
            upload, "image", MAX_IMAGE_BYTES, "an image", "Image"
        )
        total_image_bytes += len(data)
        if total_image_bytes > MAX_TOTAL_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Those photos are too large together (max "
                    f"{MAX_TOTAL_IMAGE_BYTES // (1024 * 1024)} MB in total)."
                ),
            )
        loaded_images.append((data, mime))

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
            loaded_images, text, prior,
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
