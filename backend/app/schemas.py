from datetime import date as date_type
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MealCreate(BaseModel):
    date: date_type
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)


class Meal(MealCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FoodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    serving_size: float = Field(gt=0, description="grams per serving")
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    source: Literal["user", "openfoodfacts"] = "user"


class Food(FoodCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class OFFProduct(BaseModel):
    """A normalized Open Food Facts search result (macros per serving_size grams)."""
    name: str
    brand: str | None = None
    serving_size: float
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None
    source: Literal["openfoodfacts"] = "openfoodfacts"


# A weigh-in cannot be in the future, but "today" on the server is UTC and the
# user may be up to a day ahead of it. One day of slack keeps someone in
# UTC+13 from being told their morning weigh-in is in the future, while still
# catching a mistyped year or month.
FUTURE_DATE_GRACE_DAYS = 1

# Above the heaviest weight ever recorded for a human, so a misplaced decimal
# point is rejected and every real value is accepted.
MAX_WEIGHT_KG = 635


class WeightEntryCreate(BaseModel):
    date: date_type
    weight_kg: float = Field(gt=0, le=MAX_WEIGHT_KG)

    @field_validator("date")
    @classmethod
    def not_in_future(cls, value: date_type) -> date_type:
        limit = date_type.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS)
        if value > limit:
            raise ValueError("weigh-in date cannot be in the future")
        return value


class WeightEntry(WeightEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class WeightTrendPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date_type
    weight_kg: float
    trend_kg: float


class WeightTrend(BaseModel):
    """Smoothed weight history. `weekly_rate_kg` is null when there are too few
    weigh-ins to fit one; `point_count` is how many the numbers are built from,
    so the UI can show it rather than imply more certainty than there is."""

    points: list[WeightTrendPoint]
    latest_trend_kg: float | None = None
    weekly_rate_kg: float | None = None
    point_count: int


class Settings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    calorie_goal: float = Field(gt=0)
    protein_goal: float = Field(gt=0)
    carbs_goal: float = Field(gt=0)
    fat_goal: float = Field(gt=0)
    track_carbs: bool
    track_fat: bool
    # Defaulted, unlike the goals: clients written before this field existed
    # still PUT a valid body.
    weight_unit: Literal["kg", "lb"] = "kg"


class DayTotals(BaseModel):
    date: date_type
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None


class AnalyticsSummary(BaseModel):
    days: list[DayTotals]
    totals: dict[str, float]
    averages: dict[str, float]


class ImportResult(BaseModel):
    inserted: int
    skipped_duplicates: int
    skipped_invalid: int


# NOTE: no numeric Field constraints here — this schema is sent to the LLM as a
# structured-output schema, and Gemini rejects JSON Schema numeric bounds
# (exclusiveMinimum etc.). Values are reviewed by the user before saving anyway.
class AnalyzedItem(BaseModel):
    """One detected food, with macros for the estimated portion eaten."""
    name: str
    portion_grams: float
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None
    confidence: Literal["high", "medium", "low"]


class MacroRange(BaseModel):
    low: float
    estimate: float
    high: float


class MealAnalysis(BaseModel):
    """Provider-neutral result of an AI meal analysis."""
    meal_name: str
    items: list[AnalyzedItem]
    assumptions: list[str]
    calories: MacroRange
    protein: MacroRange
    carbs: MacroRange | None = None
    fat: MacroRange | None = None
    confidence: Literal["high", "medium", "low"]
    explanation: str
    # What the model heard, when the user recorded a voice note. Lets the UI
    # show it back so a misheard word is visible before the macros are trusted.
    transcript: str | None = None
    clarifying_question: str | None = None


class MealAnalysisResponse(MealAnalysis):
    analysis_id: int


class TranscriptionResponse(BaseModel):
    """A voice note turned into text the user can edit before analysing."""

    transcript: str


class AnalysisLink(BaseModel):
    meal_id: int


class AIProbe(BaseModel):
    """What one minimal live call to the AI provider actually did."""

    # "rejected" rather than "bad_key" on purpose: an invalid key, a retired
    # model id and the EEA region block are all HTTP 400, and the expensive
    # lesson of the July outage was that the status code cannot tell them
    # apart — only the message body can. That is what `message` is for.
    status: Literal[
        "ok",
        "rate_limited",
        "rejected",
        "upstream_5xx",
        "unreachable",
        "internal_error",
        "not_configured",
        "quota_exhausted",
    ]
    message: str | None = None
    latency_ms: int | None = None
    cached: bool = False
    age_seconds: int | None = None


class AIStatus(BaseModel):
    """Enough to answer "is the AI down, and why" in one request.

    /api/health returns 200 in under a second and reports nothing about the
    provider — it did so throughout both outages. This is the endpoint that
    would have ended each of them in one call.
    """

    configured: bool
    model: str
    fallback_model: str | None = None
    # The pinned SDK's own version. google-genai's transitive dependencies are
    # not pinned, so a rebuild can resolve a pydantic or httpx the SDK no longer
    # works against; seeing the version here beats reading Render build logs.
    sdk_version: str
    probe: AIProbe | None = None


class Announcement(BaseModel):
    """One release note. `id` is stable forever: the frontend stores it to
    remember the user already dismissed this note."""

    id: str
    date: date_type
    title: str
    body: str


class AnnouncementsResponse(BaseModel):
    # `banner` is a live status/outage notice (env-driven, usually null);
    # `items` are the committed release notes, newest first.
    banner: str | None = None
    items: list[Announcement]
