"""AI meal analysis via Google Gemini.

This is the only module aware of the AI provider: routers and the frontend
depend on the provider-neutral MealAnalysis schema and the MealAIError hierarchy
below, so switching providers later means rewriting this file and changing env
vars, nothing else. services/email.py holds the other end of the same contract
for the email provider.
"""
import asyncio
import gc
import logging
import os
import random
import ssl
import time
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from ..env import env_float, env_int
from ..schemas import Food, MealAnalysis

logger = logging.getLogger(__name__)

API_KEY_ENV = "GEMINI_API_KEY"
MODEL_ENV = "MEAL_AI_MODEL"
FALLBACK_MODEL_ENV = "MEAL_AI_FALLBACK_MODEL"
DEADLINE_ENV = "MEAL_AI_DEADLINE_S"
MAX_ATTEMPTS_ENV = "MEAL_AI_MAX_ATTEMPTS"
# Kept current deliberately: Google retires models on a schedule and a retired
# id fails every request with a 4xx. Override with MEAL_AI_MODEL to switch
# without a deploy.
DEFAULT_MODEL = "gemini-3.5-flash"
# Overload is per-model serving pool, so an older generation is usually still
# answering while the newest one returns 503 — an estimate from a slightly
# weaker model beats the "enter macros manually" dead end. Quotas are per model
# too, so on the free tier every model in the chain is another day's allowance.
# MEAL_AI_FALLBACK_MODEL takes a comma-separated list; set it empty to disable.
DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"

# Retries are bounded by the DEADLINE, not by an attempt count. Gemini's
# overload 503 is an instant rejection — measured at ~150ms in production — so
# the budget is spent waiting between attempts, not making them. A fixed
# attempt count therefore burns the entire allowance in a second or two and
# gives up with almost all of it unused, which is exactly the failure a user
# works around by pressing the button again for a minute. Waiting is the whole
# strategy; the loop just does it for them.
#
# ⚠️ "Instant" only holds on a mild overload. On a bad one (2026-10-04/05) the
# same 503 took 2-20 s and a 504 13-30 s, so a single refusal can eat a third of
# the budget -- which is what the *_MIN_ATTEMPT_S floors below account for.
RETRY_BASE_DELAY = 1.0  # seconds, doubled per attempt
RETRY_MAX_DELAY = 8.0  # ceiling, so late attempts stay frequent enough to matter

# Attempts per user action, whatever the deadline still allows. Google counts a
# refused attempt against the per-day quota exactly like an answered one
# (measured 2026-10-04: two answers and ~12 overload failures, then refused for
# the day), and the free tier is 20 a day per model for the whole app -- so an
# uncapped minute of retries let one analysis on a bad Gemini day spend
# everyone's AI. On a paid key a refused attempt costs no money, which is why
# MEAL_AI_MAX_ATTEMPTS can raise it from the dashboard.
ANALYZE_MAX_ATTEMPTS = 4
TRANSCRIBE_MAX_ATTEMPTS = 3
REVIEW_MAX_ATTEMPTS = 2

# Google's per-day quotas reset at midnight Pacific -- its documented rule, and
# measured 2026-10-04. NOT what the 429 says: its retryDelay points at 00:00 UTC,
# and a key that trusted it got two more calls and another refusal.
QUOTA_RESET_TZ = "America/Los_Angeles"
# PST. Off by an hour during US daylight time, which only matters if the
# runtime has no tzdata -- and every figure built from this says "about".
QUOTA_RESET_FALLBACK_OFFSET_HOURS = -8
# A model refused for the day is skipped until the reset, but asked again after
# at most this long: switching billing on lifts the quota mid-day, and the app
# should find that out by itself rather than at midnight Pacific or a restart.
EXHAUSTED_RECHECK = timedelta(hours=1)

# Seam for the clock the retry deadline is measured against. Named so tests can
# swap in a virtual clock — the loop is bounded by wall time, so a stubbed sleep
# that didn't move the clock would spin until the backoff overflowed. Patching
# this beats patching time.monotonic globally, which the test client also uses.
_now = time.monotonic
# The wall clock, for the one thing that is about calendar days: the per-day
# quota. Its own seam for the same reason as _now.
_utcnow = lambda: datetime.now(timezone.utc)  # noqa: E731

# Models Google has refused for the day, and until when to believe it. Module
# state is a real cache here for the same reason as the probe cache in
# routers/ai.py: Render runs one instance. A restart forgets it, which costs one
# refused attempt per model -- this saves attempts, it is not what enforces
# anything.
_exhausted: dict[str, datetime] = {}

# Per-attempt deadline. Without one the SDK inherits httpx's default of no
# timeout at all, so a connection Google accepts and then never answers pins a
# worker on our single free instance until the platform kills the request.
# Milliseconds: HttpOptions.timeout is documented in ms and the SDK divides by
# 1000 before handing it to httpx.
ANALYZE_TIMEOUT_MS = 30_000
TRANSCRIBE_TIMEOUT_MS = 12_000
PROBE_TIMEOUT_MS = 10_000
# The review is text in, text out -- no images, no audio, no schema -- so it is
# the cheapest call this app makes and the one least worth waiting on. Nothing
# is lost by giving up: the page it decorates has already rendered in full.
REVIEW_TIMEOUT_MS = 15_000

# How long one user action may keep trying before reporting failure. This is the
# real control: at ~150ms per rejection and a backoff capped at 8s, a minute
# buys roughly ten attempts spread across the outage instead of four crammed
# into the first two seconds. The frontend's own budget must exceed this.
ANALYZE_DEADLINE_S = 60
# Shorter because a voice note is the first step of a longer flow — the user is
# waiting to type, not waiting for an answer.
TRANSCRIBE_DEADLINE_S = 25
REVIEW_DEADLINE_S = 30

# The least time an attempt needs to have a real chance of answering. Another
# attempt starts only if this much budget is left after its backoff, because an
# attempt that cannot finish inside the deadline still reaches Google -- and a
# request Google received counts against the per-day quota whether or not we
# wait for it. Measured from production logs on 2026-10-04/05: answers took
# 9-23.5 s, and an overloaded model's refusals were NOT instant (503s 2-20 s,
# 504s 13-30 s). That day a voice-note retry started with ~1 s of budget left
# and a refine's fourth attempt with ~16 s; both were refused, spent a quota
# slot each, and the second stretched the wait to 74.5 s against a 60 s budget.
# Replayed against that day's log, these floors drop 3 of 22 requests and no
# answer. The first attempt always runs: it is the one the user asked for.
ANALYZE_MIN_ATTEMPT_S = 20
TRANSCRIBE_MIN_ATTEMPT_S = 10
REVIEW_MIN_ATTEMPT_S = 10


class MealAIError(Exception):
    """Base for provider failures, so callers never import provider symbols."""


class MealAIRateLimited(MealAIError):
    """Provider quota or per-minute rate limit exhausted."""


class MealAIDailyQuotaExhausted(MealAIRateLimited):
    """The provider's allowance for the DAY is spent, not the minute's.

    A subclass, so everything that treats a 429 as "refused before inference"
    -- the refund, the probe's classification -- keeps doing so. What differs
    is what the user is told: "try again in a minute" is false for hours.
    """

    def __init__(self, message: str, resets_at: datetime):
        super().__init__(message)
        self.resets_at = resets_at


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


REVIEW_PROMPT = """\
You rewrite already-computed facts about one person's week of food logging \
into a short, plain summary. You are a phrasing layer and nothing else.

ABSOLUTE RULES — every one of these matters more than the writing:
- Use ONLY the facts given below. Never introduce a number that is not in them.
- Never calculate anything. Not a difference, not a percentage, not a total, \
not a projection.
- Never give advice, recommendations, targets, goals or suggestions. Do not \
tell the reader what to eat, how much to eat, what to change, or what to do \
next — not even gently, and not even if a fact seems to invite it.
- Never speculate about why anything happened.
- Where a fact says something could not be measured, say so plainly rather \
than guessing at it or leaving it out.
- Do not congratulate, encourage, warn or admonish. Neutral and calm.

FORMAT: at most two short paragraphs of plain prose. No headings, no bullet \
points, no emoji, no sign-off. Address the reader as "you".

THE FACTS:
"""


def quota_ids(exc: Exception) -> list[str]:
    """The quota ids a 429 names, read from its structured QuotaFailure.

    ⚠️ Never from the message text. The first per-day guard (in
    scripts/compare_estimates.py) searched the prose for "PerDay" and stopped a
    run on what was a per-minute refusal -- the model answered again seconds
    later. The structured id is the only signal that has never been wrong.
    """
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    return [
        violation.get("quotaId", "")
        for item in (error or {}).get("details", []) or []
        if isinstance(item, dict)
        for violation in item.get("violations", []) or []
        if isinstance(violation, dict)
    ]


def is_daily_quota(exc: Exception) -> bool:
    """True for a per-day refusal (e.g. GenerateRequestsPerDayPerProjectPerModel-
    FreeTier). Anything else -- including a 429 with no structure at all -- reads
    as per-minute, the conservative answer: it is never retried on the same model.
    """
    return any("PerDay" in quota for quota in quota_ids(exc))


def _quota_tz() -> timezone | ZoneInfo:
    try:
        return ZoneInfo(QUOTA_RESET_TZ)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=QUOTA_RESET_FALLBACK_OFFSET_HOURS))


def next_quota_reset(now: datetime | None = None) -> datetime:
    """The next midnight Pacific, in UTC: when Google's per-day quotas reset."""
    now = now or _utcnow()
    local = now.astimezone(_quota_tz())
    midnight = datetime.combine(
        local.date() + timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo
    )
    return midnight.astimezone(timezone.utc)


def _is_exhausted(model: str) -> bool:
    until = _exhausted.get(model)
    if until is None:
        return False
    if _utcnow() >= until:
        del _exhausted[model]
        return False
    return True


def _mark_exhausted(model: str) -> None:
    now = _utcnow()
    _exhausted[model] = min(next_quota_reset(now), now + EXHAUSTED_RECHECK)


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
        if exc.code == 429 and is_daily_quota(exc):
            # Expected and frequent on the free tier, and the quota id says
            # everything a traceback would -- so one line, not a stack.
            resets_at = next_quota_reset()
            logger.warning(
                "Gemini daily quota exhausted (model=%s, quota=%s, resets_at=%s)",
                model, ",".join(quota_ids(exc)), resets_at.isoformat(timespec="minutes"),
            )
            raise MealAIDailyQuotaExhausted(str(exc), resets_at) from exc
        logger.exception(
            "Gemini rejected the request (model=%s, code=%s, quota=%s)",
            model, exc.code, ",".join(quota_ids(exc)) or None,
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


# Worth another go on the SAME model. Deliberately NOT MealAIRateLimited: a
# 429 means that model's window is full -- for the minute or for the day -- so
# asking it again inside the window only deepens the refusal. _call_with_retry
# moves a 429 to the next model instead, which has quotas of its own.
# Deliberately NOT MealAIInternalError: a drifted dependency raises the same TypeError every
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


def _rss_mb() -> int | None:
    """This process's resident memory in MB, or None where /proc doesn't exist.

    Logged beside every provider outcome because the free plan's memory graph
    is coarse and averaged, and the 2026-09-29 restart was a ratchet across
    attempts: a figure per call is what shows whether it is climbing again.
    """
    try:
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


async def _generate(model: str, contents: list, config: types.GenerateContentConfig):
    """One generate_content call, on a client closed when it returns.

    Built per call, not hoisted: a key or model changed in the dashboard is
    meant to take effect without a restart, and that only holds while the
    client is constructed from the env every time. Closed explicitly because
    the SDK otherwise defers that to __del__, which schedules it as a task on
    whatever loop happens to be running.

    ⚠️ **The gc.collect() is the fix for an outage, not tidiness.** Every
    attempt leaves an httpx Response in a reference cycle with its own stream,
    and hanging off it is the Request carrying the whole encoded body -- about
    1.3x the photos in base64, plus the base64 strings themselves. Only the
    cyclic collector can free that, and it triggers on *object counts*: a few
    objects holding tens of megabytes never trip it. So each photo attempt
    ratcheted the process up by roughly its payload and never came back, and on
    2026-09-29 a Gemini overload (2-4 attempts per analysis) took the 512 MB
    instance over its limit in five minutes. Collecting before each attempt
    bounds what is outstanding to the last attempt's garbage. Measured locally:
    a full collection on the loaded app is ~20 ms, against a call of seconds.
    """
    gc.collect()
    async with genai.Client(api_key=_env(API_KEY_ENV)).aio as client:
        return await client.models.generate_content(
            model=model, contents=contents, config=config
        )


def _models() -> list[str]:
    """The model chain: preferred first, then each fallback in order.

    Deduped so setting both env vars to the same id doesn't quietly double
    every request's worst-case latency for no extra chance of success.
    """
    chain = [_env(MODEL_ENV) or DEFAULT_MODEL]
    # os.environ rather than _env, because the distinction that matters here is
    # set-to-empty (an operator turning the fallback off) versus never set.
    if FALLBACK_MODEL_ENV in os.environ:
        fallbacks = _env(FALLBACK_MODEL_ENV)
    else:
        fallbacks = DEFAULT_FALLBACK_MODEL
    for fallback in fallbacks.split(","):
        fallback = fallback.strip()
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


def _max_attempts(default: int) -> int:
    """Attempts per user action, overridable from the dashboard.

    Below one means nothing an operator could want -- zero attempts would turn
    the AI off with an outage message -- so it keeps the default, as _deadline
    does. The kill switch for AI is AI_GLOBAL_DAILY_LIMIT=0.
    """
    value = env_int(MAX_ATTEMPTS_ENV, default)
    return value if value >= 1 else default


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
    operation,
    *,
    timeout_ms: int,
    deadline_s: float,
    max_attempts: int,
    min_attempt_s: float,
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

    Two budgets bound it, whichever runs out first: the deadline (how long the
    user waits) and max_attempts (how much of the per-day quota one action may
    spend, since Google counts refused attempts too). The deadline is enforced
    when an attempt is *started*, never by cutting one short: an attempt only
    begins if min_attempt_s of budget remain after its backoff. Cutting a
    running attempt would throw away a request Google has already counted. A 429 takes its model out
    of the rotation for this call and moves on at once -- no sleep, because the
    next model's quota is its own -- and a per-day 429 also takes it out for
    later calls, until the reset or the hourly re-check.
    """
    http_options = types.HttpOptions(timeout=timeout_ms)
    pool = [model for model in _models() if not _is_exhausted(model)]
    if not pool:
        resets_at = next_quota_reset()
        logger.warning(
            "Every Gemini model is out of quota for the day; not calling "
            "(resets_at=%s)", resets_at.isoformat(timespec="minutes"),
        )
        raise MealAIDailyQuotaExhausted("Every model's daily quota is spent.", resets_at)
    deadline_s = _deadline(deadline_s)
    max_attempts = _max_attempts(max_attempts)
    started = _now()
    turn = 0
    last: MealAIError | None = None

    for attempt in range(1, max_attempts + 1):
        # Alternate through the chain rather than exhausting the primary first,
        # so a sustained overload reaches the other serving pool on attempt two
        # instead of after the budget is half gone.
        model = pool[turn % len(pool)]
        turn += 1
        delay = _backoff(attempt)
        # Whether there is room for another attempt after this one. Decided up
        # front so the last failure is the one that pays for a full traceback;
        # re-checked after the attempt, which may itself have taken a while.
        final = (
            attempt == max_attempts
            or (_now() - started) + delay + min_attempt_s > deadline_s
        )

        try:
            with _provider_errors(model, final=final):
                response = await operation(model, http_options)
        except MealAIRateLimited as exc:
            last = exc
            if isinstance(exc, MealAIDailyQuotaExhausted):
                _mark_exhausted(model)
            # Out of the rotation; turn steps back so the model that slid into
            # this slot is the one asked next.
            pool.remove(model)
            turn -= 1
            if not pool:
                raise
            logger.info(
                "Gemini %s refused (%s); trying %s now",
                model, type(exc).__name__, pool[turn % len(pool)],
            )
            continue
        except _RETRYABLE as exc:
            last = exc
        else:
            logger.info(
                "Gemini answered (model=%s, attempts=%d, rss_mb=%s)",
                model, attempt, _rss_mb(),
            )
            return model, response

        elapsed = _now() - started
        if attempt == max_attempts:
            break
        if elapsed + delay + min_attempt_s > deadline_s:
            # Said out loud because it is the line that explains a give-up with
            # attempts to spare -- and the prod check that this floor holds.
            logger.info(
                "Not retrying Gemini: %.0fs of budget left after the backoff, under "
                "the %.0fs an attempt needs (model=%s, attempt %d of %d)",
                deadline_s - elapsed - delay, min_attempt_s, model, attempt, max_attempts,
            )
            break
        logger.info(
            "Retrying Gemini in %.1fs (model=%s, attempt %d of %d, %.0fs of budget left)",
            delay, model, attempt + 1, max_attempts, deadline_s - elapsed,
        )
        await asyncio.sleep(delay)

    logger.warning(
        "Giving up on Gemini after %.1fs and %d attempts (deadline=%.0fs, "
        "max_attempts=%d, rss_mb=%s)",
        _now() - started, attempt, deadline_s, max_attempts, _rss_mb(),
    )
    raise last


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


def analysis_config(http_options: types.HttpOptions) -> types.GenerateContentConfig:
    """The request settings every meal analysis is sent with.

    Its own function so scripts/compare_estimates.py sends exactly what the app
    sends: an A/B of photo sizes or models is only evidence about production if
    the prompt, schema and temperature cannot drift between the two.
    """
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=MealAnalysis,
        temperature=0.2,
        http_options=http_options,
    )


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
        return await _generate(
            model,
            _build_contents(
                images, text, prior_analysis, audio_bytes, audio_mime,
                library_foods,
            ),
            analysis_config(http_options),
        )

    # Parsing stays outside the retry: a response that arrived and failed to
    # parse already burned tokens, and a second call bills them again for the
    # same broken output.
    model, response = await _call_with_retry(
        call,
        timeout_ms=ANALYZE_TIMEOUT_MS,
        deadline_s=ANALYZE_DEADLINE_S,
        max_attempts=ANALYZE_MAX_ATTEMPTS,
        min_attempt_s=ANALYZE_MIN_ATTEMPT_S,
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
        return await _generate(
            model,
            [
                types.Part.from_bytes(
                    data=audio_bytes, mime_type=audio_mime or "audio/webm"
                ),
                TRANSCRIPTION_PROMPT,
            ],
            # Transcription has one right answer; don't let it paraphrase.
            types.GenerateContentConfig(temperature=0.0, http_options=http_options),
        )

    model, response = await _call_with_retry(
        call,
        timeout_ms=TRANSCRIBE_TIMEOUT_MS,
        deadline_s=TRANSCRIBE_DEADLINE_S,
        max_attempts=TRANSCRIBE_MAX_ATTEMPTS,
        min_attempt_s=TRANSCRIBE_MIN_ATTEMPT_S,
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


async def phrase_review(facts: Sequence[str]) -> str:
    """Computed facts in, one short paragraph out. No numbers of its own.

    **This is a phrasing layer and the constraint is the whole design.** Every
    figure in `facts` was computed and clamped by `app/review.py` before it got
    here, and the model is forbidden to compute, recommend or add. That is not
    politeness: every safety guarantee in this app is a clamp on a number, and
    prose has no clamp -- a model that answered "eat 1,200 kcal" would route
    around the most carefully reasoned code in the repo in one sentence.

    ⚠️ The rules live in the prompt, so **nothing here can enforce them**. Tests
    all use a stub and stay green whatever a real model does, which is exactly
    the Phase 20 finding: a prompt rule is only ever proven by a live call.

    temperature 0.2 rather than 0.0: this is the one call in the app whose job
    is wording rather than a fact, and a strict zero makes it recite the input
    almost verbatim, which buys nothing over rendering the sentences directly.
    """
    async def call(model: str, http_options: types.HttpOptions):
        return await _generate(
            model,
            [REVIEW_PROMPT + "\n".join(f"- {fact}" for fact in facts)],
            types.GenerateContentConfig(temperature=0.2, http_options=http_options),
        )

    model, response = await _call_with_retry(
        call,
        timeout_ms=REVIEW_TIMEOUT_MS,
        deadline_s=REVIEW_DEADLINE_S,
        max_attempts=REVIEW_MAX_ATTEMPTS,
        min_attempt_s=REVIEW_MIN_ATTEMPT_S,
    )

    try:
        text = (response.text or "").strip()
    except Exception:  # safety-blocked responses raise on .text
        text = ""
    if not text:
        candidates = getattr(response, "candidates", None)
        finish = candidates[0].finish_reason if candidates else None
        logger.error(
            "Gemini returned no review summary (model=%s, finish_reason=%s, facts=%d)",
            model, finish, len(facts),
        )
        raise MealAIBadResponse("The AI did not return a summary. Try again.")
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
        "fallback_model": ", ".join(chain[1:]) or None,
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
    with _provider_errors(model):
        await _generate(
            model,
            [PROBE_PROMPT],
            types.GenerateContentConfig(
                temperature=0.0,
                http_options=types.HttpOptions(timeout=PROBE_TIMEOUT_MS),
            ),
        )
    return model
