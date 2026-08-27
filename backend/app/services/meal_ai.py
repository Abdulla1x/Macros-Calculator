"""AI meal analysis via Google Gemini.

This is the only module aware of the AI provider: routers and the frontend
depend on the provider-neutral MealAnalysis schema and the MealAIError hierarchy
below, so switching providers later means rewriting this file and changing env
vars, nothing else. services/email.py holds the other end of the same contract
for the email provider.
"""
import asyncio
import logging
import os
import random
import ssl
import time
from collections.abc import Sequence
from contextlib import contextmanager

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from ..env import env_float
from ..schemas import Food, MealAnalysis

logger = logging.getLogger(__name__)

API_KEY_ENV = "GEMINI_API_KEY"
MODEL_ENV = "MEAL_AI_MODEL"
FALLBACK_MODEL_ENV = "MEAL_AI_FALLBACK_MODEL"
DEADLINE_ENV = "MEAL_AI_DEADLINE_S"
# Kept current deliberately: Google retires models on a schedule and a retired
# id fails every request with a 4xx. Override with MEAL_AI_MODEL to switch
# without a deploy.
DEFAULT_MODEL = "gemini-3.5-flash"
# Overload is per-model serving pool, so an older generation is usually still
# answering while the newest one returns 503 — an estimate from a slightly
# weaker model beats the "enter macros manually" dead end. Set
# MEAL_AI_FALLBACK_MODEL empty to disable.
DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"

# Retries are bounded by the DEADLINE, not by an attempt count. Gemini's
# overload 503 is an instant rejection — measured at ~150ms in production — so
# the budget is spent waiting between attempts, not making them. A fixed
# attempt count therefore burns the entire allowance in a second or two and
# gives up with almost all of it unused, which is exactly the failure a user
# works around by pressing the button again for a minute. Waiting is the whole
# strategy; the loop just does it for them.
RETRY_BASE_DELAY = 1.0  # seconds, doubled per attempt
RETRY_MAX_DELAY = 8.0  # ceiling, so late attempts stay frequent enough to matter

# Seam for the clock the retry deadline is measured against. Named so tests can
# swap in a virtual clock — the loop is bounded by wall time, so a stubbed sleep
# that didn't move the clock would spin until the backoff overflowed. Patching
# this beats patching time.monotonic globally, which the test client also uses.
_now = time.monotonic

# Per-attempt deadline. Without one the SDK inherits httpx's default of no
# timeout at all, so a connection Google accepts and then never answers pins a
# worker on our single free instance until the platform kills the request.
# Milliseconds: HttpOptions.timeout is documented in ms and the SDK divides by
# 1000 before handing it to httpx.
ANALYZE_TIMEOUT_MS = 30_000
TRANSCRIBE_TIMEOUT_MS = 12_000
PROBE_TIMEOUT_MS = 10_000

# How long one user action may keep trying before reporting failure. This is the
# real control: at ~150ms per rejection and a backoff capped at 8s, a minute
# buys roughly ten attempts spread across the outage instead of four crammed
# into the first two seconds. The frontend's own budget must exceed this.
ANALYZE_DEADLINE_S = 60
# Shorter because a voice note is the first step of a longer flow — the user is
# waiting to type, not waiting for an answer.
TRANSCRIBE_DEADLINE_S = 25


class MealAIError(Exception):
    """Base for provider failures, so callers never import provider symbols."""


class MealAIRateLimited(MealAIError):
    """Provider quota or per-minute rate limit exhausted."""


class MealAIUnavailable(MealAIError):
    """Provider answered with an HTTP 5xx — its outage, and waiting fixes it."""


class MealAIUnreachable(MealAIError):
    """No answer at all: DNS, TCP, TLS, or our own deadline expired.

    Split from MealAIUnavailable because the two need different people. A 5xx
    is Google's problem; this one is our network, our region, or a timeout we
    set too tight — and folding both into one exception is what made the last
    outage a three-day guess instead of a log line.
    """


class MealAIInternalError(MealAIError):
    """Our own SDK or plumbing raised something we don't recognise.

    google-genai's transitive dependencies are not pinned, so a rebuild can
    resolve a pydantic or httpx the pinned SDK no longer works against. That
    fails 100% of calls with a TypeError from inside site-packages, which looks
    exactly like a provider outage unless it is named separately.
    """


class MealAIBadRequest(MealAIError):
    """Provider rejected the request: bad key, retired model, or bad payload.

    Retrying won't help; this needs an operator to look at the logs.
    """


class MealAIBadResponse(MealAIError):
    """Provider replied with something that isn't a usable MealAnalysis."""


SYSTEM_PROMPT = """\
You are the nutrition analysis engine of a macro-tracking app. Given any
combination of a meal photo, a spoken description, and a typed description,
estimate the nutrition of what the user actually ate.

Rules:
- ALWAYS produce your best estimate. Never decline because information is
  missing; make sensible assumptions instead, and list every assumption you
  made as a short phrase in `assumptions` (e.g. "2 slices eaten",
  "regular crust", "cooked with ~1 tbsp oil").
- The user's words (typed or spoken) are ground truth and override the image
  (e.g. "I only ate half" halves portions; "the beef is 90% lean" lowers fat).
- Several photos are DIFFERENT VIEWS OF ONE MEAL unless the user says
  otherwise: a plate from another angle, a close-up, or the packaging and its
  nutrition label. Count each food ONCE, no matter how many photos show it.
  Use the extra views to identify foods and judge portions more precisely, and
  prefer a legible nutrition label over estimating from appearance. Only treat
  photos as separate additional foods when the user's words say so (e.g. "and
  I also had this") — and when you do, say so in `assumptions`.
- Estimate the amount actually EATEN, not the amount served, whenever the
  user says so.
- With no photo, work from the description alone: assume standard preparations
  and typical restaurant or home portions for any detail the user left out,
  and record each such guess in `assumptions`.
- `items`: one entry per distinct food. `portion_grams` and the macros are
  for that portion (not per 100 g).
- The user may attach foods from their saved library, listed below with exact
  macros per a stated serving size. Those numbers are facts, not estimates: if
  an attached food is part of this meal, do NOT re-estimate its macros. Set
  that item's `matched_food_name` to the attached name exactly as written,
  estimate only `portion_grams`, and scale the given macros to that portion
  (item macros stay per-portion, as above). Leave `matched_food_name` null for
  every item that is not one of them, and never invent a name that is not in
  the list.
- The `calories`/`protein`/`carbs`/`fat` ranges cover the whole meal:
  `estimate` is your single best guess (approximately the sum of the items);
  `low`/`high` reflect genuine uncertainty — wide when preparation or
  portions are unclear, narrow when the user gave precise details.
- `confidence`: "high" = clearly identifiable foods and portions;
  "low" = hidden ingredients, unclear portions, or heavy sauces/dressings.
- `explanation`: one or two plain sentences telling the user what you are
  confident about and what you are not.
- `transcript`: when audio is provided, a concise verbatim transcription of
  what the user said. Null whenever there is no audio.
- `clarifying_question`: null in almost all cases. Set it ONLY when the input
  is unusable (photo too dark, blurry, or not food; audio inaudible; or a
  description too vague to place, like "food") — and even then still return
  your best-effort estimate.
- When a previous analysis is provided, refine it using the new information
  rather than starting over, and keep facts the user already corrected.
"""

TRANSCRIPTION_PROMPT = """\
Transcribe the speech in this audio.

- Output only the transcription: no preamble, commentary, or quotation marks.
- Keep the speaker's own words and units ("a hundred grams", "two slices").
- Write food names the way they are conventionally spelled.
- If there is no intelligible speech, output nothing at all.
"""


@contextmanager
def _provider_errors(model: str, *, final: bool = True):
    """Translate provider exceptions into the neutral hierarchy, logging why.

    This is the only place the provider's own words are recorded — callers get
    a MealAIError with no google.genai types attached, so the router stays
    provider-agnostic.

    `final` decides how loudly to log: only the last attempt pays for a full
    traceback, because during an outage the alternative is a dozen identical
    stacks burying the line that says what finally happened.
    """
    log = logger.exception if final else logger.warning
    try:
        yield
    except genai_errors.ClientError as exc:
        # 4xx is our side: exhausted quota, or a request/config the API refuses
        # (invalid key, retired model id, a region where the free tier isn't
        # offered). Never retried, so always logged in full.
        logger.exception(
            "Gemini rejected the request (model=%s, code=%s)", model, exc.code
        )
        if exc.code == 429:
            raise MealAIRateLimited(str(exc)) from exc
        raise MealAIBadRequest(str(exc)) from exc
    except genai_errors.ServerError as exc:
        log(
            "Gemini server error (model=%s, code=%s, final=%s)",
            model, exc.code, final,
        )
        raise MealAIUnavailable(str(exc)) from exc
    except (httpx.TransportError, ssl.SSLError, OSError) as exc:
        # Never got a reply. httpx.TransportError covers ConnectError,
        # ReadTimeout, ConnectTimeout and the rest of that family in one line —
        # including our own HttpOptions deadline expiring — and OSError catches
        # the socket-level failures httpx doesn't wrap.
        log(
            "Gemini unreachable (model=%s, kind=%s, final=%s)",
            model, type(exc).__name__, final,
        )
        raise MealAIUnreachable(f"{type(exc).__name__}: {exc}") from exc
    except MealAIError:
        raise
    except Exception as exc:
        # Not the provider refusing us and not the network: the SDK itself
        # raised. Named rather than folded into "unavailable" because retrying
        # cannot fix it, and the operator — not the user — is the one who can.
        logger.exception(
            "Gemini call raised an unexpected error (model=%s, kind=%s)",
            model, type(exc).__name__,
        )
        raise MealAIInternalError(f"{type(exc).__name__}: {exc}") from exc


# Worth another go. Deliberately NOT MealAIRateLimited: a 429 means we are
# already sending too much and the limit window is 60s wide, so two more
# requests inside it make the thing we are being limited for worse — the "try
# again in a minute" the user already sees is the correct remedy. Deliberately
# NOT MealAIInternalError: a drifted dependency raises the same TypeError every
# time. Deliberately NOT MealAIBadResponse: that response arrived and burned
# tokens, and asking again bills them twice for the same garbage.
_RETRYABLE = (MealAIUnavailable, MealAIUnreachable)


def _env(name: str) -> str:
    """Read an env var, tolerating how dashboards mangle pasted values.

    A key with a trailing newline or wrapping quotes is rejected by Google as
    `API key not valid` (HTTP 400) — indistinguishable from a revoked key, and
    invisible in a dashboard's masked field.
    """
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def is_configured() -> bool:
    return bool(_env(API_KEY_ENV))


def _models() -> list[str]:
    """The model chain: preferred first, fallback second.

    Deduped so setting both env vars to the same id doesn't quietly double
    every request's worst-case latency for no extra chance of success.
    """
    chain = [_env(MODEL_ENV) or DEFAULT_MODEL]
    # os.environ rather than _env, because the distinction that matters here is
    # set-to-empty (an operator turning the fallback off) versus never set.
    if FALLBACK_MODEL_ENV in os.environ:
        fallback = _env(FALLBACK_MODEL_ENV)
    else:
        fallback = DEFAULT_FALLBACK_MODEL
    if fallback and fallback not in chain:
        chain.append(fallback)
    return chain


def _deadline(default: float) -> float:
    """How long to keep trying, overridable from the dashboard.

    Same escape hatch as MEAL_AI_MODEL: during a provider overload the one knob
    you want is "keep trying longer", and waiting on a build to turn it is the
    wrong cost. Raising it also means raising the frontend's budget, which is
    why it is not raised lightly.
    """
    value = env_float(DEADLINE_ENV, default)
    return value if value > 0 else default


def _backoff(attempt: int) -> float:
    """Exponential up to a ceiling, then jittered down.

    The ceiling matters more than the growth: unbounded doubling would spend the
    back half of the budget asleep, when what a flapping provider needs is
    frequent sampling. Jitter keeps concurrent users from retrying in lockstep
    and handing Google back the burst that caused the overload.
    """
    return min(RETRY_BASE_DELAY * 2 ** (attempt - 1), RETRY_MAX_DELAY) * random.uniform(
        0.5, 1.0
    )


async def _call_with_retry(
    operation, *, timeout_ms: int, deadline_s: float
) -> tuple[str, object]:
    """Run one provider call, retrying only what another attempt can fix.

    Returns the model that actually answered alongside its response, because
    with a fallback chain "which model produced this" stops being a constant —
    and it is the first thing you want in the log when the output is unusable.

    The retry lives here rather than in the router on purpose: the router has
    already reserved exactly one quota slot for this user action, and one user
    action must stay one slot. A 5xx is refused before inference, so retrying
    costs nothing billable — which is also why an arrived-but-unusable response
    is pointedly not retryable.
    """
    http_options = types.HttpOptions(timeout=timeout_ms)
    models = _models()
    deadline_s = _deadline(deadline_s)
    started = _now()
    attempt = 0
    last: MealAIError | None = None

    while True:
        attempt += 1
        # Alternate through the chain rather than exhausting the primary first,
        # so a sustained overload reaches the other serving pool on attempt two
        # instead of after the budget is half gone.
        model = models[(attempt - 1) % len(models)]
        delay = _backoff(attempt)
        # Whether there is room for another attempt after this one. Decided up
        # front so the last failure is the one that pays for a full traceback.
        final = (_now() - started) + delay >= deadline_s

        try:
            with _provider_errors(model, final=final):
                return model, await operation(model, http_options)
        except _RETRYABLE as exc:
            last = exc

        elapsed = _now() - started
        if final or elapsed + delay >= deadline_s:
            logger.warning(
                "Giving up on Gemini after %.1fs and %d attempts (deadline=%.0fs)",
                elapsed, attempt, deadline_s,
            )
            raise last
        logger.info(
            "Retrying Gemini in %.1fs (model=%s, attempt %d, %.0fs of budget left)",
            delay, model, attempt + 1, deadline_s - elapsed,
        )
        await asyncio.sleep(delay)


def _default_instruction(image_count: int, has_audio: bool) -> str:
    """What to say when the user gave media but no words to go with it."""
    # Plural matters here: "the photo" in front of four images invites the model
    # to answer about one of them, which is the quiet version of this going
    # wrong — a plausible estimate built from a quarter of the evidence.
    photos = "the photo" if image_count == 1 else "the photos"
    if image_count and has_audio:
        return f"Analyze the meal in {photos}, using the spoken description."
    if has_audio:
        return "Analyze the meal described in the audio."
    return f"Analyze the meal in {photos}."


def _library_block(foods: Sequence[Food]) -> str:
    """Attached library foods, rendered as facts rather than as suggestions.

    One compact line per food is what keeps this affordable: roughly 12-14
    tokens each, re-sent on *every* attempt, since analyze_meal rebuilds the
    request per retry. MAX_ATTACHED_FOODS in routers/ai.py is therefore the real
    bound on what attaching can add to the bill, and this format is the other
    half of that arithmetic.

    A macro the user never recorded is said in words instead of being left
    blank. carbs and fat are nullable on a foods row, the model is meant to
    estimate the missing one itself, and an empty slot in a list of exact
    figures reads as zero -- which would silently claim a food has no fat.
    """
    lines = ["The user's saved food library -- these numbers are exact, not estimates:"]
    for food in foods:
        # :g so a whole number prints as "165" rather than "165.0"; these lines
        # are read by a model that copies what it sees.
        macros = [f"{food.calories:g} kcal", f"{food.protein:g} g protein"]
        missing = [
            label
            for label, value in (("carbs", food.carbs), ("fat", food.fat))
            if value is None
        ]
        macros += [
            f"{value:g} g {label}"
            for label, value in (("carbs", food.carbs), ("fat", food.fat))
            if value is not None
        ]
        line = f'- "{food.name}" -- per {food.serving_size:g} g: ' + ", ".join(macros)
        if missing:
            line += f" ({' and '.join(missing)} not recorded)"
        lines.append(line)
    return "\n".join(lines)


def _build_contents(
    images: Sequence[tuple[bytes, str | None]],
    text: str | None,
    prior_analysis: MealAnalysis | None,
    audio_bytes: bytes | None = None,
    audio_mime: str | None = None,
    library_foods: Sequence[Food] | None = None,
) -> list:
    parts: list = []
    # Order is preserved: the user picked these in a sequence, and the prompt
    # tells the model they are views of one meal, so a stable order is what
    # makes "the first photo" mean anything in a follow-up correction.
    for image_bytes, image_mime in images:
        parts.append(
            types.Part.from_bytes(
                data=image_bytes, mime_type=image_mime or "image/jpeg"
            )
        )
    if audio_bytes:
        parts.append(
            types.Part.from_bytes(
                data=audio_bytes, mime_type=audio_mime or "audio/webm"
            )
        )

    # The library block is deliberately kept out of the instruction list below,
    # and that separation is load-bearing. `if not instructions` is what gives a
    # photo-only request something to act on; folding facts into the same list
    # would satisfy that check and send a photo, a table of macros, and no
    # instruction telling the model what to do with either.
    lines: list[str] = []
    if library_foods:
        lines.append(_library_block(library_foods))

    instructions: list[str] = []
    if prior_analysis is not None:
        instructions.append(
            "Previous analysis to refine (JSON): "
            + prior_analysis.model_dump_json()
        )
    if text:
        instructions.append(f"User's description/notes: {text}")
    if not instructions:
        instructions.append(_default_instruction(len(images), bool(audio_bytes)))
    # Reference material first, the user's own words last. The prompt declares
    # those words ground truth that overrides the image, so they sit closest to
    # the answer rather than buried above a list of foods.
    lines.extend(instructions)
    parts.append("\n\n".join(lines))
    return parts


async def analyze_meal(
    images: Sequence[tuple[bytes, str | None]],
    text: str | None,
    prior_analysis: MealAnalysis | None = None,
    *,
    audio_bytes: bytes | None = None,
    audio_mime: str | None = None,
    library_foods: Sequence[Food] | None = None,
) -> MealAnalysis:
    async def call(model: str, http_options: types.HttpOptions):
        # Built per attempt, not hoisted: a key or model changed in the
        # dashboard is meant to take effect without a restart, and that only
        # holds while the client is constructed from the env on every call.
        client = genai.Client(api_key=_env(API_KEY_ENV))
        return await client.aio.models.generate_content(
            model=model,
            contents=_build_contents(
                images, text, prior_analysis, audio_bytes, audio_mime,
                library_foods,
            ),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MealAnalysis,
                temperature=0.2,
                http_options=http_options,
            ),
        )

    # Parsing stays outside the retry: a response that arrived and failed to
    # parse already burned tokens, and a second call bills them again for the
    # same broken output.
    model, response = await _call_with_retry(
        call, timeout_ms=ANALYZE_TIMEOUT_MS, deadline_s=ANALYZE_DEADLINE_S
    )

    # response.parsed is populated when the SDK validated the schema itself;
    # fall back to validating the raw JSON text.
    if isinstance(response.parsed, MealAnalysis):
        return response.parsed
    try:
        raw = response.text or ""
    except Exception:  # safety-blocked responses raise on .text
        raw = ""
    try:
        return MealAnalysis.model_validate_json(raw)
    except ValidationError as exc:
        # Almost always a truncated response (thinking tokens ate the budget)
        # or a safety block, so record why the model stopped.
        # getattr: never let the diagnostic itself throw and mask the real error.
        candidates = getattr(response, "candidates", None)
        finish = candidates[0].finish_reason if candidates else None
        # audio_mime/audio_bytes are here because a mislabelled container is
        # indistinguishable from any other bad response from the client side.
        logger.error(
            "Gemini returned an unusable response (model=%s, finish_reason=%s, "
            "chars=%d, audio_mime=%s, audio_bytes=%s)",
            model, finish, len(raw), audio_mime, len(audio_bytes or b""),
        )
        raise MealAIBadResponse("Model returned no usable JSON.") from exc


async def transcribe_audio(audio_bytes: bytes, audio_mime: str | None) -> str:
    """A voice note in, plain text out — no estimating, no JSON.

    Kept separate from analyze_meal so the transcript can be shown and edited
    *before* it reaches the estimate: a misheard ingredient is then a typo the
    user fixes, rather than a wrong number they have to notice afterwards.
    """
    async def call(model: str, http_options: types.HttpOptions):
        client = genai.Client(api_key=_env(API_KEY_ENV))
        return await client.aio.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(
                    data=audio_bytes, mime_type=audio_mime or "audio/webm"
                ),
                TRANSCRIPTION_PROMPT,
            ],
            # Transcription has one right answer; don't let it paraphrase.
            config=types.GenerateContentConfig(
                temperature=0.0, http_options=http_options
            ),
        )

    model, response = await _call_with_retry(
        call, timeout_ms=TRANSCRIBE_TIMEOUT_MS, deadline_s=TRANSCRIBE_DEADLINE_S
    )

    try:
        text = (response.text or "").strip()
    except Exception:  # safety-blocked responses raise on .text
        text = ""
    if not text:
        # Usually silence or an inaudible recording, but a safety block lands
        # here too — record which, since the user only sees "nothing heard".
        candidates = getattr(response, "candidates", None)
        finish = candidates[0].finish_reason if candidates else None
        # The mime and byte count separate "the browser sent a container Gemini
        # couldn't read" from "the recording really was silent" — the two look
        # identical to the user, and only one of them is our bug.
        logger.error(
            "Gemini returned no transcript (model=%s, finish_reason=%s, "
            "audio_mime=%s, audio_bytes=%d)",
            model, finish, audio_mime, len(audio_bytes),
        )
        raise MealAIBadResponse("No speech was recognised in the recording.")
    return text


def provider_info() -> dict[str, str | None]:
    """What the router may say about the provider without importing it.

    Keeps this the only module that knows google.genai exists, while still
    letting /api/ai/status report the SDK version — the one fact that separates
    "Google is down" from "a rebuild resolved a dependency the pinned SDK no
    longer works against".
    """
    chain = _models()
    return {
        "model": chain[0],
        "fallback_model": chain[1] if len(chain) > 1 else None,
        "sdk_version": genai.__version__,
    }


PROBE_PROMPT = "Reply with the single word: ok"


async def probe() -> str:
    """The smallest call that proves the whole path, raising what a real one would.

    No schema, no media, no retry and no fallback: this runs when something is
    already wrong, so it has to report the *first* model's actual state rather
    than paper over it, and the shared quota is the thing you least want to
    spend diagnosing an outage. Returns the model it reached.

    The response body is deliberately never inspected — the question is "did the
    request complete", and checking .text would report a healthy provider as
    broken whenever a thinking model spent its budget on thoughts.
    """
    model = _models()[0]
    client = genai.Client(api_key=_env(API_KEY_ENV))
    with _provider_errors(model):
        await client.aio.models.generate_content(
            model=model,
            contents=[PROBE_PROMPT],
            config=types.GenerateContentConfig(
                temperature=0.0,
                http_options=types.HttpOptions(timeout=PROBE_TIMEOUT_MS),
            ),
        )
    return model
