from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .banking import MAX_DAY_DELTA_KCAL, MAX_PLAN_DAYS


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
    # Response-only, and deliberately not on MealCreate: the client states what
    # was eaten, the server states when the row last changed. Declared without
    # a default so that a row missing the attribute raises here instead of
    # silently reporting an unedited meal -- the from_attributes trap. Null is
    # the honest value for a meal with no recorded edit, not a missing one.
    updated_at: datetime | None


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


# Steps bound. Unlike MAX_WATER_GOAL_ML this carries no health opinion -- there
# is no amount of walking this app declines to help anyone do. It exists only
# to catch a figure that is not a step count at all, which is nearly always a
# stray digit, and it sits well past any distance a person covers in a day.
MAX_STEPS_PER_DAY = 200_000


class StepEntryCreate(BaseModel):
    date: date_type
    # ge=0, not gt=0. Water refuses a zero because nobody logs drinking no
    # water, but a day with no walking on it is a real day worth recording --
    # and a count typed in error has to be correctable down to zero.
    steps: int = Field(ge=0, le=MAX_STEPS_PER_DAY)

    @field_validator("date")
    @classmethod
    def not_in_future(cls, value: date_type) -> date_type:
        # Same grace as a weigh-in and a water log: the server's today may be a
        # day behind the user's.
        limit = date_type.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS)
        if value > limit:
            raise ValueError("step count date cannot be in the future")
        return value


class StepEntry(StepEntryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None


class StepDay(BaseModel):
    """Everything the steps card needs, in one response.

    There is no StepGoalBasis here and the absence is deliberate. A water goal
    is derived from body weight, so it has arithmetic that has to travel with
    it; a step goal is either a number the user typed or no number at all.
    `goal` is None in the second case and the card drops its bar rather than
    drawing progress towards an invented target.

    `logged` carries what `steps` cannot. Since zero is a legal count, "logged
    a zero" and "has not logged" are two different days that both report
    `steps == 0`, and only one of them should offer to be cleared.
    """

    date: date_type
    steps: int
    logged: bool
    goal: int | None = None
    # The walking estimate and the weight it was worked out from, together --
    # the standing rule that no derived number reaches the screen without its
    # inputs beside it. Both None when there is no weigh-in to derive from.
    burn_kcal: float | None = None
    burn_weight_kg: float | None = None


# Supplement bounds. Like MAX_STEPS_PER_DAY these carry no health opinion --
# this app has no business telling anyone what to take. They exist so the list
# stays a list a person can tick off, and so a paste accident cannot store a
# novel in a name column.
MAX_SUPPLEMENTS = 30
MAX_SUPPLEMENT_TIMES = 6
MAX_SUPPLEMENT_NAME = 100
MAX_SUPPLEMENT_DOSE = 60

# "HH:MM", 24-hour. A plain string rather than datetime.time because it is a
# *label on a schedule*, not an instant: it has no date and no timezone, and
# every consumer -- the unique index, the log row, the client's clock
# comparison -- wants the two digits either side of the colon.
SupplementTime = Annotated[
    str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
]


class SupplementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SUPPLEMENT_NAME)
    # Free text and optional: doses have no common unit (IU, mg, ml, capsules),
    # so a number-plus-enum would be missing whatever someone actually takes.
    # Displayed beside the name, never computed with.
    dose: str | None = Field(default=None, max_length=MAX_SUPPLEMENT_DOSE)
    times: list[SupplementTime] = Field(
        min_length=1, max_length=MAX_SUPPLEMENT_TIMES
    )
    # Present on create so the same model can serve PUT, where pausing is the
    # whole point. Defaults true: a supplement you are adding is one you intend
    # to take.
    active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Trim, and refuse a name that is only whitespace.

        `min_length=1` alone accepts " ", which then renders as a blank row on
        the tick list -- a dose you cannot identify is one you cannot honestly
        tick. It would also defeat the case-insensitive unique index, since
        " " and "  " are different strings.
        """
        value = value.strip()
        if not value:
            raise ValueError("supplement name cannot be blank")
        return value

    @field_validator("dose")
    @classmethod
    def strip_dose(cls, value: str | None) -> str | None:
        """An all-whitespace dose is no dose, and stores as NULL rather than "".

        Two ways to say "unset" in one column is how a display ends up with a
        stray separator nobody can find the source of.
        """
        if value is None:
            return None
        return value.strip() or None

    @field_validator("times")
    @classmethod
    def sorted_and_unique(cls, value: list[str]) -> list[str]:
        """A schedule, not an ordering the user chose.

        Sorting is what lets the card render the day in order without sorting it
        again in the client, and de-duplicating stops "08:00, 08:00" from
        claiming two doses that are one -- the second could never be ticked
        separately, since the log's unique index spans exactly this value.
        """
        return sorted(set(value))


class Supplement(SupplementCreate):
    """One supplement as stored.

    Not a from_attributes model, deliberately, and this is the fourth time the
    same trap has come up: the ORM column is `times_json` (TEXT) and this field
    is `times` (list). Reading attributes off the row would hand Pydantic a JSON
    string for a list field and 500 every response, so routers/supplements.py
    builds this explicitly in `_supplement_out`, the sibling of `_settings_out`,
    `_template_out` and `_user_out`.
    """

    id: int
    created_at: datetime | None = None


class SupplementSlot(BaseModel):
    """One scheduled dose on one day, and whether it has been taken.

    `off_schedule` is the interesting flag. A slot normally comes from the
    supplement's current schedule, but a slot that is only here because a log
    row exists -- the supplement has since been paused, or its time moved -- is
    still part of that day's truth and must not silently vanish from a day that
    was fully taken. It is rendered as history rather than as something due.
    """

    supplement_id: int
    name: str
    dose: str | None = None
    time: SupplementTime
    taken: bool
    off_schedule: bool = False


class SupplementDay(BaseModel):
    """Everything the supplements card needs, in one response.

    `taken` and `scheduled` are the card's value and goal. Neither is a derived
    measurement the way a water goal is -- they are counts of the rows below --
    but they travel with the slots for the same reason: one definition, resolved
    once, rather than a client that re-counts and can disagree.

    Nothing here says whether a dose is *due*. That needs the user's wall clock,
    which the server does not have and this app stores no timezone for, so it is
    the one derived value in the daily trackers that is honestly the client's to
    compute. See components/SupplementsCard.tsx.
    """

    date: date_type
    taken: int
    scheduled: int
    slots: list[SupplementSlot] = []


class SupplementLogCreate(BaseModel):
    supplement_id: int
    date: date_type
    time: SupplementTime

    @field_validator("date")
    @classmethod
    def not_in_future(cls, value: date_type) -> date_type:
        # Same grace as a weigh-in, a water log and a step count: the server's
        # today may be a day behind the user's.
        limit = date_type.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS)
        if value > limit:
            raise ValueError("supplement log date cannot be in the future")
        return value


# How far ahead a plan may reach. MAX_PLAN_DAYS caps how many days a plan
# covers; this caps how far away they are, which is a different thing -- 14 days
# scattered across the next decade would satisfy the first bound and be
# meaningless. A year is well past any real plan and still catches a mistyped
# year, which is the failure this is actually for.
MAX_PLAN_HORIZON_DAYS = 365


class CaloriePlanCreate(BaseModel):
    """Ask for calories to be moved between days.

    `dates` are the days that ABSORB the change, and never include the event
    day. For a planned day that means the days funding it; for a compensating
    one, the days taking on the difference. The event day is separate because
    the two kinds treat it differently -- a planned day is itself adjusted and
    gets a row, a compensated one is already logged and does not.

    There is no amount for a compensating plan, deliberately. How far the day
    ran over is measured from the meals on it against the target that day
    actually had, server-side, at the moment the plan is written. Accepting a
    figure from the client would let a stale number -- read before the last
    meal was logged, or before the goal changed -- become the plan.

    The split across `dates` is server-side for the same reason: the parts have
    to provably re-add to the whole, and that is not a promise a client can
    make on this app's behalf.
    """

    kind: Literal["planned", "compensating"]
    event_date: date_type
    dates: list[date_type] = Field(min_length=1, max_length=MAX_PLAN_DAYS)
    # Signed, and only meaningful for a planned day: positive for a bigger day
    # funded by the others, negative for a smaller one whose savings they take
    # on. Ignored for `compensating`, where the amount is measured rather than
    # asked for.
    calorie_delta: float | None = Field(
        default=None, ge=-MAX_DAY_DELTA_KCAL, le=MAX_DAY_DELTA_KCAL,
        allow_inf_nan=False,
    )

    @field_validator("dates", "event_date")
    @classmethod
    def within_the_horizon(cls, value):
        # The mirror image of every other date validator in this file. Those
        # refuse the future because a weigh-in or a meal can only describe
        # something that has happened; this is the first feature whose dates are
        # deliberately ahead of today, so what it refuses is a date so far out
        # that it is certainly a typo.
        limit = date_type.today() + timedelta(days=MAX_PLAN_HORIZON_DAYS)
        days = value if isinstance(value, list) else [value]
        for day in days:
            if day > limit:
                raise ValueError(
                    f"a plan cannot reach more than {MAX_PLAN_HORIZON_DAYS} "
                    f"days ahead"
                )
        return value


class PlanDay(BaseModel):
    """One day's effective targets — the four numbers its rings are drawn against.

    Deliberately not `Settings`, whose four goals are `gt=0`. That model is a
    response model as well as a request one, which is the entire reason
    `targets.MIN_WRITTEN_GOAL` exists: a zero that was legal to write turns
    every later read into a 500. These are `ge=0` because a shaved day's carb
    target genuinely can floor at zero, and this model is built by hand in the
    router rather than from an ORM row, so nothing about it is stored.

    `calorie_delta` is None on an ordinary day. It is not zero: "no plan touches
    this day" and "a plan touches it and moves it by nothing" are different
    facts, and only one of them has something to cancel.
    """

    date: date_type
    calorie_goal: float = Field(ge=0, allow_inf_nan=False)
    protein_goal: float = Field(ge=0, allow_inf_nan=False)
    carbs_goal: float = Field(ge=0, allow_inf_nan=False)
    fat_goal: float = Field(ge=0, allow_inf_nan=False)
    calorie_delta: float | None = None
    kind: Literal["planned", "compensating"] | None = None
    event_date: date_type | None = None


class CaloriePlan(BaseModel):
    """A whole plan: the day it is about, and every day adjusted for it."""

    event_date: date_type
    kind: Literal["planned", "compensating"]
    created_at: datetime | None = None
    days: list[PlanDay] = []
    # What the plan moves in total. Zero for a planned group by definition --
    # shown anyway, because a number the user can check beats a promise that it
    # balances.
    total_delta: float = 0
    # Whether anything is still left to cancel. False once every adjusted day is
    # in the past, which is not the same as the plan not existing.
    can_cancel: bool = False


class DaySurplus(BaseModel):
    """How far a finished day ran from its target, and what it was measured against.

    `consumed_calories` and `reference_calories` travel separately rather than
    pre-subtracted, because the reference is the weak half and the screen has to
    be able to say so. No historical target is stored anywhere in this app --
    `settings.calorie_goal` is one mutable column that `apply_auto_targets`
    rewrites on every weigh-in -- so the reference here is what that day's
    target is *now*, plus any adjustment already on it. If the goal has moved
    since, this number moves with it.

    `meal_count` is the guard against the worst reading of all: zero meals
    logged is not a day of eating nothing, and a surplus computed from it would
    invite a large and entirely fictional compensation.
    """

    date: date_type
    consumed_calories: float
    reference_calories: float
    surplus_calories: float
    meal_count: int
    # The adjustment already on that day, if any -- so "you went 300 over"
    # means over the target the day actually had, not over the stock goal.
    calorie_delta: float | None = None


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
    # None here means "I have no step goal", not "derive one for me" -- the
    # one place where two neighbouring nullable settings mean opposite things
    # by their emptiness. See the column comment in models.py. The field name
    # matches its column exactly, so from_attributes reads it directly and this
    # one needs no _settings_out() conversion.
    steps_goal: int | None = Field(default=None, gt=0, le=MAX_STEPS_PER_DAY)

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

    Averages divide by days that actually have meals, not by calendar days in
    the range. A day with no meals means the user did not log, not that they ate
    nothing, so counting it as zero understates intake.

    Each macro divides by its own count, in `average_days` — carbs and fat are
    nullable on a meal, so they can be recorded on fewer days than calories and
    protein were. Both travel with the numbers: `logged_days` is how many days
    have any meal at all, `average_days[macro]` is the denominator that macro's
    average actually used, and no rate should be shown without it.
    """

    days: list[DayTotals]
    totals: dict[str, float]
    averages: dict[str, float]
    logged_days: int = 0
    average_days: dict[str, int] = {}


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
    steps: int = 0
    # Two counts rather than one, because they answer different questions: how
    # many things someone tracks is setup, how many doses they have ticked is
    # use. Counts only -- never a name, see the privacy note on the router.
    supplements: int = 0
    supplement_logs: int = 0
