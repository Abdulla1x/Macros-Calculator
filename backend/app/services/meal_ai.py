"""AI meal analysis via Google Gemini.

This is the ONLY provider-aware module: routers and the frontend depend on the
provider-neutral MealAnalysis schema and the MealAIError hierarchy below, so
switching providers later means rewriting this file and changing env vars,
nothing else.
"""
import logging
import os

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from ..schemas import MealAnalysis

logger = logging.getLogger(__name__)

API_KEY_ENV = "GEMINI_API_KEY"
MODEL_ENV = "MEAL_AI_MODEL"
# Kept current deliberately: Google retires models on a schedule and a retired
# id fails every request with a 4xx. Override with MEAL_AI_MODEL to switch
# without a deploy.
DEFAULT_MODEL = "gemini-3.5-flash"


class MealAIError(Exception):
    """Base for provider failures, so callers never import provider symbols."""


class MealAIRateLimited(MealAIError):
    """Provider quota or per-minute rate limit exhausted."""


class MealAIUnavailable(MealAIError):
    """Provider is down or unreachable — retrying later may succeed."""


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
- Estimate the amount actually EATEN, not the amount served, whenever the
  user says so.
- With no photo, work from the description alone: assume standard preparations
  and typical restaurant or home portions for any detail the user left out,
  and record each such guess in `assumptions`.
- `items`: one entry per distinct food. `portion_grams` and the macros are
  for that portion (not per 100 g).
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


def _env(name: str) -> str:
    """Read an env var, tolerating how dashboards mangle pasted values.

    A key with a trailing newline or wrapping quotes is rejected by Google as
    `API key not valid` (HTTP 400) — indistinguishable from a revoked key, and
    invisible in a dashboard's masked field.
    """
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def is_configured() -> bool:
    return bool(_env(API_KEY_ENV))


def _default_instruction(has_image: bool, has_audio: bool) -> str:
    """What to say when the user gave media but no words to go with it."""
    if has_image and has_audio:
        return "Analyze the meal in the photo, using the spoken description."
    if has_audio:
        return "Analyze the meal described in the audio."
    return "Analyze the meal in the photo."


def _build_contents(
    image_bytes: bytes | None,
    image_mime: str | None,
    text: str | None,
    prior_analysis: MealAnalysis | None,
    audio_bytes: bytes | None = None,
    audio_mime: str | None = None,
) -> list:
    parts: list = []
    if image_bytes:
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

    lines: list[str] = []
    if prior_analysis is not None:
        lines.append(
            "Previous analysis to refine (JSON): "
            + prior_analysis.model_dump_json()
        )
    if text:
        lines.append(f"User's description/notes: {text}")
    if not lines:
        lines.append(_default_instruction(bool(image_bytes), bool(audio_bytes)))
    parts.append("\n\n".join(lines))
    return parts


async def analyze_meal(
    image_bytes: bytes | None,
    image_mime: str | None,
    text: str | None,
    prior_analysis: MealAnalysis | None = None,
    *,
    audio_bytes: bytes | None = None,
    audio_mime: str | None = None,
) -> MealAnalysis:
    model = _env(MODEL_ENV) or DEFAULT_MODEL
    client = genai.Client(api_key=_env(API_KEY_ENV))
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=_build_contents(
                image_bytes, image_mime, text, prior_analysis,
                audio_bytes, audio_mime,
            ),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=MealAnalysis,
                temperature=0.2,
            ),
        )
    except genai_errors.ClientError as exc:
        # 4xx is our side: exhausted quota, or a request/config the API refuses
        # (invalid key, retired model id). Log the provider's own words — this
        # is the only place the real reason exists.
        logger.exception("Gemini rejected the request (model=%s, code=%s)", model, exc.code)
        if exc.code == 429:
            raise MealAIRateLimited(str(exc)) from exc
        raise MealAIBadRequest(str(exc)) from exc
    except genai_errors.ServerError as exc:
        logger.exception("Gemini server error (model=%s, code=%s)", model, exc.code)
        raise MealAIUnavailable(str(exc)) from exc
    except Exception as exc:
        logger.exception("Gemini call failed (model=%s)", model)
        raise MealAIUnavailable(str(exc)) from exc

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
        logger.error(
            "Gemini returned an unusable response (model=%s, finish_reason=%s, chars=%d)",
            model, finish, len(raw),
        )
        raise MealAIBadResponse("Model returned no usable JSON.") from exc
