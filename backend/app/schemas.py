from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated, Literal

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    # Bounded so an oversized "token" can't be hashed and queried. Real ones are
    # 43 characters — secrets.token_urlsafe(32) base64url-encoded, unpadded.
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    """A bare human-readable message, for endpoints with nothing to return."""

    detail: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    # Display convenience only -- it decides whether the client bothers
    # rendering the admin page. The server authorizes every /api/admin request
    # independently via require_admin; a client that lies about this flag gets
    # a 403 and nothing else.
    #
    # Defaulted, like Settings.weight_unit and AnalyticsSummary.logged_days, so
    # a client written before this field existed still parses the response.
    # NOTE: the default is also why every construction site must pass it
    # explicitly -- see _user_out in auth/router.py.
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# Why allow_inf_nan=False appears on every float that reaches a Float column,
# here and on FoodCreate and Settings below:
#
# `ge=0` does not exclude infinity -- `inf >= 0` is True -- and json.loads
# accepts the bare token `Infinity`, so a hand-written request could park a
# non-finite value in the database. One such row then fails two different ways
# at once: GET /api/data/export/all returns a plain dict, so the raw float
# reaches Starlette's json.dumps(allow_nan=False) and 500s, while the list and
# settings endpoints serialize through Pydantic, whose ser_json_inf_nan default
# quietly rewrites it to `null` -- for a field the client's types.ts declares as
# `number`. The silent half is the worse half.
#
# Rejecting at the boundary is what fixes both. Once nothing non-finite gets in,
# nothing downstream has to know about it.
class MealCreate(BaseModel):
    date: date_type
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0, allow_inf_nan=False)
    protein: float = Field(ge=0, allow_inf_nan=False)
    carbs: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class Meal(MealCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


# Bounds the size of MealTemplate.items_json. Named for the same reason
# MAX_IMAGES is: the number is a policy choice, not a fact, and the comment is
# where the reasoning lives. Thirty ingredients is far past any real meal.
MAX_TEMPLATE_ITEMS = 30


class TemplateItem(BaseModel):
    """One ingredient row inside a saved template.

    The bounds here are stricter than MealCreate's on purpose. These values are
    serialized into a Text column and read back out through
    /api/data/export/all, and json.dumps turns float('inf') into the bare token
    `Infinity`, which is not valid JSON -- one such row would corrupt the
    export for the entire account. Where a value is stored decides how much
    damage bad input can do.
    """

    name: str = Field(min_length=1, max_length=200)
    weight_grams: float = Field(gt=0, allow_inf_nan=False)
    serving_size: float = Field(gt=0, allow_inf_nan=False)
    calories: float = Field(ge=0, allow_inf_nan=False)
    protein: float = Field(ge=0, allow_inf_nan=False)
    carbs: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class MealTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0, allow_inf_nan=False)
    protein: float = Field(ge=0, allow_inf_nan=False)
    carbs: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    # The count bound lives on the list so the rejection is Pydantic's 422
    # rather than a hand-rolled check in the router.
    items: list[TemplateItem] = Field(
        default_factory=list, max_length=MAX_TEMPLATE_ITEMS
    )


class MealTemplate(MealTemplateCreate):
    # Deliberately NOT from_attributes, unlike every other X(XCreate) pair in
    # this file. The ORM row has no `items` attribute -- it has `items_json` --
    # and Pydantic's response to a missing attribute on a defaulted field is to
    # substitute the default, silently. Every template would come back with
    # `items: []` and nothing would raise. This is the Phase 2 `is_admin` bug
    # in a new costume, so the router builds this model explicitly instead:
    # see _template_out in routers/meal_templates.py.
    id: int
    # Whether the POST created a new template or replaced an existing one with
    # the same name. Overwriting a food is a correction; overwriting a template
    # destroys an ingredient list, so the client says which happened.
    created: bool = False


class FoodCreate(BaseModel):
    # allow_inf_nan=False for the reason given above MealCreate.
    name: str = Field(min_length=1, max_length=200)
    serving_size: float = Field(
        gt=0, allow_inf_nan=False, description="grams per serving"
    )
    calories: float = Field(ge=0, allow_inf_nan=False)
    protein: float = Field(ge=0, allow_inf_nan=False)
    carbs: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat: float | None = Field(default=None, ge=0, allow_inf_nan=False)
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
    # No allow_inf_nan=False here, deliberately: MAX_WEIGHT_KG already closes
    # it. `inf` fails the upper bound and `nan` fails every comparison it is
    # given, so both are rejected before the keyword would ever be consulted.
    # Adding it anyway would imply the schemas that do carry it were unsafe for
    # some reason other than having no upper bound.
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


# Taller than the tallest human ever recorded, so a misplaced decimal point is
# rejected and every real value is accepted -- the MAX_WEIGHT_KG argument.
MAX_HEIGHT_CM = 272

# Deliberately far wider than the 1 kg/week that `calculations.py` will clamp
# to. The clamp *explains itself* in the response; a 422 does not. Someone who
# types -3 should be told why they are getting -1, not handed a validation
# error that reads like the field is broken. This bound only catches input that
# is not a rate at all.
MAX_INPUT_GOAL_RATE_KG_PER_WEEK = 5.0

# Older than the oldest verified human. Same job as the two bounds above.
MAX_AGE_YEARS = 122

# Water bounds. All three are refusals of input that is not a plausible amount
# of water, not opinions about how much anyone should drink.
#
# The goal ceiling is the one with a real reason behind it rather than a
# rounding: sustained intake much above 10 litres a day outruns the kidneys'
# ability to excrete it, and hyponatraemia is a genuine harm. A tracker should
# not accept a goal it would be dangerous to meet.
MAX_WATER_GOAL_ML = 10_000.0
# One tap should not be able to log more than a large bottle.
MAX_WATER_QUICK_ADD_ML = 2_000.0
# A single hand-typed entry, which may legitimately be a jug at a restaurant.
MAX_WATER_ENTRY_ML = 5_000.0
# How many quick-add buttons fit on a phone without wrapping into a grid.
MAX_WATER_QUICK_ADDS = 4

# Each element bounded, not just the list. `list[float]` with a bound on the
# list alone would accept [inf, nan, -1] as three perfectly good floats.
WaterQuickAddMl = Annotated[float, Field(gt=0, le=MAX_WATER_QUICK_ADD_ML)]


class WaterEntryCreate(BaseModel):
    # Bounded above, so no allow_inf_nan -- the WeightEntryCreate argument.
    date: date_type
    ml: float = Field(gt=0, le=MAX_WATER_ENTRY_ML)

    @field_validator("date")
    @classmethod
    def not_in_future(cls, value: date_type) -> date_type:
        # Same grace as a weigh-in, and for the same reason: the server's today
        # may be a day behind the user's.
        limit = date_type.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS)
        if value > limit:
            raise ValueError("water log date cannot be in the future")
        return value


class WaterEntry(WaterEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # What "undo" removes: the entries come back newest-first so the client
    # never has to sort them to find the last one.
    created_at: datetime | None = None


class WaterGoalBasis(BaseModel):
    """Where the day's goal came from, so the card can show its working.

    Mirrors TdeeBasis in intent: a derived number arrives with its inputs
    attached, and "we had nothing to derive from" is stated rather than hidden
    behind a plausible-looking figure.
    """

    source: Literal["custom", "weight", "default"]
    ml_per_kg: float | None = None
    weight_kg: float | None = None


class WaterDay(BaseModel):
    """Everything the water card needs, in one response.

    The goal travels with the total deliberately. It is derived from the user's
    trend weight, and deriving it client-side would be a second definition of
    the same number -- the thing this codebase keeps refusing to have.
    """

    date: date_type
    total_ml: float
    goal_ml: float
    goal_basis: WaterGoalBasis
    entries: list[WaterEntry] = []


ACTIVITY_LEVELS = Literal["sedentary", "light", "moderate", "active", "very_active"]


class Settings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # allow_inf_nan=False for the reason given above MealCreate. `gt=0` admits
    # infinity exactly as `ge=0` does, and these are Float columns like any
    # other -- a non-finite goal would divide every progress ring on the
    # dashboard.
    calorie_goal: float = Field(gt=0, allow_inf_nan=False)
    protein_goal: float = Field(gt=0, allow_inf_nan=False)
    carbs_goal: float = Field(gt=0, allow_inf_nan=False)
    fat_goal: float = Field(gt=0, allow_inf_nan=False)
    track_carbs: bool
    track_fat: bool
    # Defaulted, unlike the goals: clients written before this field existed
    # still PUT a valid body.
    weight_unit: Literal["kg", "lb"] = "kg"

    # Body profile. Every field defaults, for the reason weight_unit does, and
    # every field name matches its column name exactly -- which is what keeps
    # `from_attributes` honest here. A response field whose name diverges from
    # its attribute silently returns the default instead of failing, the trap
    # `_user_out` and `_template_out` both exist to avoid.
    #
    # No allow_inf_nan on the two floats: each carries an upper bound, which
    # closes inf and nan already. See WeightEntryCreate.
    height_cm: float | None = Field(default=None, gt=0, le=MAX_HEIGHT_CM)
    birth_date: date_type | None = None
    sex: Literal["male", "female"] | None = None
    activity_level: ACTIVITY_LEVELS | None = None
    goal_rate_kg_per_week: float | None = Field(
        default=None,
        ge=-MAX_INPUT_GOAL_RATE_KG_PER_WEEK,
        le=MAX_INPUT_GOAL_RATE_KG_PER_WEEK,
    )
    targets_auto: bool = False

    # Water. Both default, for the reason weight_unit does.
    #
    # None is meaningful for both rather than merely absent: it means "derive
    # my goal from my weight" and "use the shipped quick-add amounts". That
    # makes them indistinguishable from "not sent" in `model_fields_set`
    # terms -- which is fine, because both are patched fields and clearing one
    # is done by sending null explicitly.
    #
    # No allow_inf_nan on either: every bound here is an upper bound, which
    # closes inf and nan already. See WeightEntryCreate.
    water_goal_ml: float | None = Field(default=None, gt=0, le=MAX_WATER_GOAL_ML)
    water_quick_adds: list[WaterQuickAddMl] | None = Field(
        default=None, min_length=1, max_length=MAX_WATER_QUICK_ADDS
    )

    @field_validator("birth_date")
    @classmethod
    def plausible_birth_date(cls, value: date_type | None) -> date_type | None:
        """A birth date in the future, or implausibly far past, is a typo.

        Modelled on WeightEntryCreate.not_in_future, and using the same UTC
        slack: the server's today may be a day behind the user's.
        """
        if value is None:
            return value
        today = date_type.today()
        if value > today + timedelta(days=FUTURE_DATE_GRACE_DAYS):
            raise ValueError("birth date cannot be in the future")
        if value < today.replace(year=today.year - MAX_AGE_YEARS):
            raise ValueError(f"birth date implies an age over {MAX_AGE_YEARS}")
        return value


class TdeeBasis(BaseModel):
    """The sample a measured TDEE rests on, or what it is still short of.

    `unavailable_reason` is None exactly when the measurement was used, and
    carries a sentence naming what is missing otherwise. It deliberately does
    **not** travel in `BodyTargets.missing`: falling back to the formula is not
    a failure, the user still gets a working target, and listing it as missing
    would make a complete profile read as incomplete forever.
    """

    logged_days: int
    weigh_ins: int
    span_days: int
    mean_intake: float | None = None
    trend_change_kg: float | None = None
    unavailable_reason: str | None = None


class BodyTargets(BaseModel):
    """What the profile implies, and what is stopping it implying more.

    Every derived number here travels with the input it came from -- the weight
    used and the date it was logged -- because none of these are measurements
    of the person. `missing` names the profile fields that are absent, so the
    UI can ask for the one that is blocking rather than showing an empty card.
    """

    missing: list[str]
    bmi: float | None = None
    bmr: float | None = None
    tdee: float | None = None
    target_calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    weight_kg: float | None = None
    weight_date: date_type | None = None
    # Set when a safety clamp moved the target away from the requested rate.
    # Shown verbatim; a target that silently disagrees with the rate the user
    # typed leaves them believing the rate.
    clamped_reason: str | None = None
    # Which method produced `tdee`. Every field here is mirrored on
    # `targets.TargetsResult`, and must stay mirrored: FastAPI runs the returned
    # dataclass through `dataclasses.asdict` before validating it here, so a
    # field this schema declares and that dataclass omits serialises silently as
    # the default below instead of failing. Phase 2 demoted every admin that
    # way and Phase 3 emptied every template.
    tdee_source: Literal["estimated", "measured"] = "estimated"
    # The formula's answer, kept even when measurement won, so the two can be
    # shown together. Agreement is reassuring and divergence is diagnostic --
    # either way it is information the user is entitled to.
    tdee_estimated: float | None = None
    tdee_basis: TdeeBasis | None = None


class DayTotals(BaseModel):
    date: date_type
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None


class AnalyticsSummary(BaseModel):
    """Per-day totals over a range, plus totals and averages.

    `averages` divide by `logged_days` — days that actually have meals — not by
    calendar days in the range. A day with no meals means the user did not log,
    not that they ate nothing, so counting it as zero understates intake.
    `logged_days` travels with the numbers so the UI can say what they are
    built from.
    """

    days: list[DayTotals]
    totals: dict[str, float]
    averages: dict[str, float]
    logged_days: int = 0


class ImportResult(BaseModel):
    inserted: int
    skipped_duplicates: int
    skipped_invalid: int


# NOTE: no numeric Field constraints here — this schema is sent to the LLM as a
# structured-output schema, and Gemini rejects JSON Schema numeric bounds
# (exclusiveMinimum etc.). Values are reviewed by the user before saving anyway.
#
# That includes allow_inf_nan=False, which the other schemas here carry. It is
# not omitted because it would break Gemini -- checked, and it emits nothing
# into the generated JSON schema at all -- but because it is not needed. Pydantic
# serializes a non-finite float to `null`, so nothing here can write `Infinity`
# into ai_analyses.analysis_json, and an AI estimate only becomes a stored macro
# by being sent back through MealCreate, which does reject it. One boundary.
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


# --- Admin metrics -----------------------------------------------------------
#
# No `from_attributes` on any of these: they are computed from aggregate
# queries, not loaded off a row, which is the same reason AnalyticsSummary and
# AIStatus omit it.
#
# Every field below is a count, a date or an account identifier. None of them
# carry user content, and that is a boundary rather than an oversight -- see the
# module docstring of routers/admin.py.


class AdminDailyCount(BaseModel):
    """One day of a single series. Days with nothing in them are still sent,
    with count 0, so a chart draws a real gap instead of interpolating across
    it."""

    date: date_type
    count: int


class AdminDailyActivity(BaseModel):
    date: date_type
    active_users: int
    meals: int


class AdminStats(BaseModel):
    """App-wide usage: how many accounts exist, and how much they are used."""

    total_users: int
    total_meals: int
    signups_7d: int
    signups_30d: int
    active_7d: int
    active_30d: int
    meals_7d: int
    # The one number with operational consequences: exhausting the global cap
    # breaks meal analysis for every user at once, not just the heavy one.
    ai_calls_today: int
    ai_global_daily_limit: int
    ai_calls_30d_by_kind: dict[str, int] = {}
    # The window the series below cover, so the client never has to assume it.
    window_days: int
    signups: list[AdminDailyCount] = []
    activity: list[AdminDailyActivity] = []


class AdminUserRow(BaseModel):
    """One account's metrics — counts and timestamps, never content.

    `last_active_at` is None for an account that has signed up and done
    nothing, which is a genuinely useful thing to be able to see.
    """

    id: int
    email: str
    created_at: datetime
    last_active_at: datetime | None = None
    meals: int = 0
    weights: int = 0
    foods: int = 0
    meal_templates: int = 0
    ai_calls: int = 0
    water_logs: int = 0
