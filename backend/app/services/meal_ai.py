"""AI meal analysis via Google Gemini.

This is the ONLY provider-aware module: routers and the frontend depend on the
provider-neutral MealAnalysis schema, so switching providers later means
rewriting this file and changing env vars, nothing else.
"""
import os

from google import genai
from google.genai import types

from ..schemas import MealAnalysis

API_KEY_ENV = "GEMINI_API_KEY"
MODEL_ENV = "MEAL_AI_MODEL"
DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """\
You are the nutrition analysis engine of a macro-tracking app. Given a meal
photo and/or a text description, estimate the nutrition of what the user
actually ate.

Rules:
- ALWAYS produce your best estimate. Never decline because information is
  missing; make sensible assumptions instead, and list every assumption you
  made as a short phrase in `assumptions` (e.g. "2 slices eaten",
  "regular crust", "cooked with ~1 tbsp oil").
- The user's text is ground truth and overrides the image (e.g. "I only ate
  half" halves portions; "the beef is 90% lean" lowers fat).
- Estimate the amount actually EATEN, not the amount served, whenever the
  text says so.
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
- `clarifying_question`: null in almost all cases. Set it ONLY when the image
  is unusable (too dark, blurry, or not food) and no text was provided —
  and even then still return your best-effort estimate.
- When a previous analysis is provided, refine it using the new information
  rather than starting over, and keep facts the user already corrected.
"""


def is_configured() -> bool:
    return bool(os.environ.get(API_KEY_ENV))


def _build_contents(
    image_bytes: bytes | None,
    image_mime: str | None,
    text: str | None,
    prior_analysis: MealAnalysis | None,
) -> list:
    parts: list = []
    if image_bytes:
        parts.append(
            types.Part.from_bytes(
                data=image_bytes, mime_type=image_mime or "image/jpeg"
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
        lines.append("Analyze the meal in the photo.")
    parts.append("\n\n".join(lines))
    return parts


async def analyze_meal(
    image_bytes: bytes | None,
    image_mime: str | None,
    text: str | None,
    prior_analysis: MealAnalysis | None = None,
) -> MealAnalysis:
    client = genai.Client(api_key=os.environ.get(API_KEY_ENV))
    response = await client.aio.models.generate_content(
        model=os.environ.get(MODEL_ENV, DEFAULT_MODEL),
        contents=_build_contents(image_bytes, image_mime, text, prior_analysis),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=MealAnalysis,
            temperature=0.2,
        ),
    )
    # response.parsed is populated when the SDK validated the schema itself;
    # fall back to validating the raw JSON text.
    if isinstance(response.parsed, MealAnalysis):
        return response.parsed
    return MealAnalysis.model_validate_json(response.text or "")
