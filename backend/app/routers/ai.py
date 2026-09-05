"""AI meal analysis: photo and/or text in, structured macro estimate out."""
import logging
import os
import time as time_module
from collections.abc import Sequence
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..calibration import CalibrationSummary, Pair, parse_estimate, summarise
from .. import keep_warm
from ..db import get_db
from ..env import env_int
from ..models import AIAnalysis, Food as FoodRow, Meal, User
from ..schemas import (
    AIProbe,
    AIStatus,
    AnalysisLink,
    Calibration,
    Food,
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
# Saved foods the user may attach to one analysis. The same kind of bound as
# MAX_IMAGES and for the same reason: the quota counts calls, so nothing else
# here limits what a single call costs. Each food is one compact line of about
# 12-14 tokens (services/meal_ai.py::_library_block) re-sent on every attempt,
# because the request is rebuilt per retry -- so ten is roughly 140 tokens
# against a ~660-token system prompt. Raising it raises the per-analysis bill.
MAX_ATTACHED_FOODS = 10
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
# The weekly review's optional rephrasing. A fourth kind rather than a share of
# the analysis budget: `_reserve_call` already counts per kind, so a review can
# never eat into the meal analyses someone actually needs.
KIND_REVIEW = "review"

DEFAULT_PROBE_DAILY_LIMIT = 10

# Three a day. The review changes once a day at most -- its window ends
# yesterday -- so this is not a rationing decision, it is a stray-loop catcher.
# One is too few: a failed read and a retry would lock someone out for the day.
DEFAULT_REVIEW_DAILY_LIMIT = 3
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
    return env_int("AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT)


def _transcribe_daily_limit() -> int:
    return env_int("AI_TRANSCRIBE_DAILY_LIMIT", DEFAULT_TRANSCRIBE_DAILY_LIMIT)


def global_daily_limit() -> int:
    return env_int("AI_GLOBAL_DAILY_LIMIT", DEFAULT_GLOBAL_DAILY_LIMIT)


def _probe_daily_limit() -> int:
    return env_int("AI_PROBE_DAILY_LIMIT", DEFAULT_PROBE_DAILY_LIMIT)


def review_daily_limit() -> int:
    return env_int("AI_REVIEW_DAILY_LIMIT", DEFAULT_REVIEW_DAILY_LIMIT)


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
    # One byte past the limit, not the whole body. `len(data) > max_bytes` is
    # still an exact test for "there was more", but an oversized upload is now
    # refused having held max_bytes + 1 rather than however much the client
    # chose to send. Reading first and measuring afterwards let any signed-up
    # account make this free instance spool an arbitrary body to disk -- and it
    # happened before _reserve_call, so it never cost them a single quota slot.
    # The CSV importers in routers/data.py already read this way.
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{noun} too large (max {max_bytes // (1024 * 1024)} MB).",
        )
    return data, upload.content_type


def _attached_foods(
    db: Session, user: User, food_ids: Sequence[int]
) -> list[Food]:
    """The caller's own library rows for the ids they attached, in the order given.

    Ids in, macros out. The client never sends the numbers, which is what makes
    the facts quoted into the prompt the *stored* facts rather than whatever a
    request claimed they were -- and scoping the lookup on user_id is the same
    rule routers/foods.py::_owned states: an id belonging to someone else is
    simply not found, so it can never be read into this account's estimate.

    A missing id is refused, not dropped. An analysis that quietly ran without a
    food the user attached still comes back looking like it used it, and there
    is no way to tell from the answer -- the "bounded input whose refusal is
    invisible" failure this project has already shipped once.
    """
    if not food_ids:
        return []
    # Deduped with order preserved: the same food attached twice is one fact,
    # not two, and every copy is billed again on every retry.
    unique = list(dict.fromkeys(food_ids))
    if len(unique) > MAX_ATTACHED_FOODS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Too many saved foods attached "
                f"(max {MAX_ATTACHED_FOODS} per analysis)."
            ),
        )
    rows = db.scalars(
        select(FoodRow).where(FoodRow.id.in_(unique), FoodRow.user_id == user.id)
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(unique):
        raise HTTPException(
            status_code=422,
            detail=(
                "One of the foods you attached is no longer in your library. "
                "Remove it and try again."
            ),
        )
    # Validated into the response schema rather than passed as ORM rows, so
    # services/meal_ai.py keeps knowing nothing about the database.
    return [Food.model_validate(by_id[food_id]) for food_id in unique]


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


def _record_timing(record: AIAnalysis, started: float) -> None:
    """Stamp how long the provider took, and what the server had been up.

    Timed around the provider call ALONE, never the whole handler. The handler
    also reads the uploaded media, and Starlette streams the request body -- so
    on a slow phone part of the *upload* is still arriving while it runs.
    Folding that in would put the user's uplink inside a number meant to
    describe Gemini, which is the exact conflation the progress bar on the other
    side of this request exists to end. It also includes _reserve_call's locking
    write, which can stall on a cold Neon and would be blamed on the provider.

    The retry budget IS included, deliberately: one user action reserves one
    quota slot and produces one wait, so a figure that excluded retries would be
    one nobody ever experienced.
    """
    record.provider_ms = int((time_module.monotonic() - started) * 1000)
    record.server_uptime_s = int(keep_warm.uptime_s())


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
    # Ids of saved foods to quote into the prompt as exact facts. Repeated parts
    # under one field name, the same shape `image` above uses -- one idiom in
    # this file for "a list in a multipart form". Only ids travel: see
    # _attached_foods for why the macros are read here rather than sent.
    food_id: list[int] = Form(default=[]),
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
    # Resolved here, ahead of the configuration check and well ahead of
    # _reserve_call: an attachment the server cannot honour is refused before it
    # can cost a quota slot, and it is refused identically whether or not a
    # provider key is set -- which is what lets the isolation and smoke checks
    # prove the ownership rule without spending a provider call.
    library_foods = _attached_foods(db, user, food_id)
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

    started = time_module.monotonic()
    try:
        analysis = await meal_ai.analyze_meal(
            loaded_images, text, prior,
            audio_bytes=audio_bytes, audio_mime=audio_mime,
            library_foods=library_foods,
        )
    except meal_ai.MealAIBadResponse as exc:
        # The model ran and burned tokens; only its output was unusable, so the
        # slot stays spent. Refunding here would make "send input that reliably
        # produces garbage" an uncapped free path to the provider.
        #
        # The row survives, so its timing does too: the provider really was
        # occupied for that long, and a p95 that dropped these would describe a
        # faster service than the one people are waiting on.
        _record_timing(record, started)
        db.commit()
        raise _provider_http_error(exc)
    except Exception as exc:
        # Refused (4xx) or unreachable (5xx) — rejected before inference, so
        # nothing was billed and a provider failure shouldn't cost the user a
        # slot.
        db.delete(record)
        db.commit()
        raise _provider_http_error(exc)

    _record_timing(record, started)
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

    started = time_module.monotonic()
    try:
        transcript = await meal_ai.transcribe_audio(audio_bytes, audio_mime)
    except meal_ai.MealAIBadResponse as exc:
        # Silence, or speech the model couldn't make out. It listened either
        # way, so the slot stays spent — otherwise uploading silence on a loop
        # would be an unmetered way to keep calling the provider. It listened
        # for real, so the timing is kept alongside the slot.
        _record_timing(record, started)
        db.commit()
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
    _record_timing(record, started)
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


def calibration_summary(db: Session, user_id: int) -> CalibrationSummary:
    """This account's estimates against the meals actually saved from them.

    Lifted out of the endpoint below because the weekly review reports one line
    of it, and two copies of this join would be two things to keep in step --
    `routers/review.py` imports it the way `routers/plan.py` already imports
    `_get_or_create` from `routers/settings.py`.

    Spends no quota by construction: it only reads rows that each already
    represent one billable call.
    """
    rows = db.execute(
        select(AIAnalysis.analysis_json, Meal.calories, Meal.protein)
        .join(Meal, Meal.id == AIAnalysis.meal_id)
        .where(
            AIAnalysis.user_id == user_id,
            AIAnalysis.kind == KIND_ANALYSIS,
            AIAnalysis.meal_id.is_not(None),
            # Both sides are ownership-checked when the link is written, so this
            # is redundant today. It is here because every other router states
            # the scope at the query rather than trusting a distant invariant.
            Meal.user_id == user_id,
        )
    ).all()

    # Counted from the table before anything is parsed, so a refusal reports the
    # true size of the log rather than the size of the subset that survived.
    analyses = db.scalar(
        select(func.count())
        .select_from(AIAnalysis)
        .where(AIAnalysis.user_id == user_id, AIAnalysis.kind == KIND_ANALYSIS)
    )

    pairs: list[Pair] = []
    unreadable = 0
    for analysis_json, saved_calories, saved_protein in rows:
        estimate = parse_estimate(analysis_json)
        if estimate is None:
            unreadable += 1
            continue
        # protein is NOT NULL on meals, but read defensively rather than assume
        # a column constraint at a distance.
        pairs.append(Pair(estimate, saved_calories, saved_protein or 0.0))

    return summarise(
        pairs,
        analyses=analyses or 0,
        linked=len(rows),
        unreadable=unreadable,
    )


@router.get("/calibration", response_model=Calibration)
def calibration(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """How this account's saved meals compare to the estimates behind them.

    Read-only, and deliberately spends no quota: every row in ai_analyses *is*
    one billable provider call, which is what `calls_today` and the admin stats
    count. Reserving a slot to answer a question about slots already spent would
    corrupt the counter it reports on.

    No date window. The corrected subset is small by nature -- correcting an
    estimate is the rare path -- and slicing it by the Analytics page's 30-day
    range would empty it for most accounts. Calibration is a property of the
    model and this user, not of a month.
    """
    return calibration_summary(db, user.id)
