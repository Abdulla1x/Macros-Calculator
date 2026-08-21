from collections.abc import Sequence
from datetime import date as date_type
from datetime import timedelta
from typing import NamedTuple

# Smoothing factor for the weight trend line. 0.25 is a chosen convention, not a
# measured constant: it weights each new weigh-in at a quarter and gives roughly
# a one-week effective window, which is the usual way to see past day-to-day
# water and gut-content swings. Change it and the trend line changes shape; no
# number here is derived from anything.
WEIGHT_TREND_ALPHA = 0.25

# The rate of change is fitted over the last 4 weeks of trend, and refuses to
# answer below a week of weigh-ins. Both are policy choices about how much data
# is enough to show a number, not statistical thresholds.
RATE_WINDOW_DAYS = 28
RATE_MIN_POINTS = 7


class TrendPoint(NamedTuple):
    """One weigh-in with its smoothed value."""

    date: date_type
    weight_kg: float
    trend_kg: float


def weight_trend(
    entries: Sequence[tuple[date_type, float]],
    alpha: float = WEIGHT_TREND_ALPHA,
) -> list[TrendPoint]:
    """Exponentially weighted moving average over logged weigh-ins.

    The EWMA steps *per entry*, not per calendar day: a gap of a week and a gap
    of a day advance the smoothing equally. That is a deliberate simplification
    — at the daily-ish cadence people actually weigh themselves the difference
    is small, and it keeps the series defined without inventing weights for days
    nobody stood on the scale. Entries are sorted by date; the first entry seeds
    the trend at its own value, so early points track raw weight closely.
    """
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")

    points: list[TrendPoint] = []
    trend: float | None = None
    for entry_date, weight in sorted(entries, key=lambda item: item[0]):
        trend = weight if trend is None else alpha * weight + (1 - alpha) * trend
        points.append(TrendPoint(entry_date, weight, round(trend, 3)))
    return points


def weekly_rate(
    trend_points: Sequence[TrendPoint],
    window_days: int = RATE_WINDOW_DAYS,
    min_points: int = RATE_MIN_POINTS,
) -> float | None:
    """kg per week, as the least-squares slope of the recent *trend* series.

    Fitted against calendar-day offsets, so missed days do not compress the
    timeline. Returns None rather than a number when the window holds fewer
    than `min_points` weigh-ins — a rate built from two readings is noise
    wearing a decimal point.
    """
    if not trend_points:
        return None

    latest = max(point.date for point in trend_points)
    cutoff = latest - timedelta(days=window_days - 1)
    window = [point for point in trend_points if point.date >= cutoff]
    if len(window) < min_points:
        return None

    origin = min(point.date for point in window)
    xs = [(point.date - origin).days for point in window]
    ys = [point.trend_kg for point in window]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:  # every point on one day — no slope to fit
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return round(slope * 7, 3)


def scale_macros(
    weight: float,
    serving_size: float,
    per_serving: dict[str, float | None],
) -> dict[str, float | None]:
    """Scale per-serving macro values to the weight actually eaten.

    Keys with None values (untracked macros) stay None.
    """
    if serving_size <= 0:
        raise ValueError("Serving size must be greater than zero")
    if weight < 0:
        raise ValueError("Weight cannot be negative")

    factor = weight / serving_size
    return {
        key: None if value is None else round(value * factor, 2)
        for key, value in per_serving.items()
    }


def total_macros(items: list[dict[str, float | None]]) -> dict[str, float | None]:
    """Sum macros across ingredients. A macro totals to None only if no
    ingredient reported it; otherwise missing values count as 0."""
    keys = ("calories", "protein", "carbs", "fat")
    totals: dict[str, float | None] = {}
    for key in keys:
        values = [item[key] for item in items if item.get(key) is not None]
        totals[key] = round(sum(values), 2) if values else None
    return totals


# --- Body profile → energy targets -------------------------------------------
#
# Read the labels on these constants literally. Exactly one group below is
# derived from published work; the rest are conventions and policy choices that
# this app picked and could just as reasonably have picked differently. Nothing
# here measures anything about the person using it -- that is Phase 5's job,
# and it replaces `estimated_tdee` rather than tuning these.

# PUBLISHED EQUATION. Mifflin MD, St Jeor ST et al. (1990), "A new predictive
# equation for resting energy expenditure in healthy individuals", Am J Clin
# Nutr 51(2):241-7. BMR = 10*kg + 6.25*cm - 5*age + s, where s is +5 for male
# and -161 for female bodies. These four numbers are the only ones in this
# section that are not our choice -- do not "tune" them.
MIFFLIN_WEIGHT_COEFFICIENT = 10.0
MIFFLIN_HEIGHT_COEFFICIENT = 6.25
MIFFLIN_AGE_COEFFICIENT = 5.0
MIFFLIN_SEX_OFFSET = {"male": 5.0, "female": -161.0}

# CONVENTION. The activity multipliers handed down with the Harris-Benedict
# equation. They are round numbers someone chose decades ago, they differ
# between sources, and a real person's true multiplier sits somewhere in a wide
# band around them. They are here because a day-one estimate needs *something*,
# not because they are accurate.
ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,      # desk job, little or no deliberate exercise
    "light": 1.375,        # light exercise 1-3 days a week
    "moderate": 1.55,      # moderate exercise 3-5 days a week
    "active": 1.725,       # hard exercise 6-7 days a week
    "very_active": 1.9,    # physical job, or training twice a day
}

# APPROXIMATION. The energy in a kilogram of body mass, used to turn a desired
# rate of change into a daily calorie delta. The real figure depends on what
# the tissue is -- fat stores roughly this, lean mass far less -- so it is a
# planning number, not a measurement.
KCAL_PER_KG = 7700.0

# CONVENTION. Atwater factors, rounded the way every nutrition label rounds
# them. Real digestible energy varies by food.
KCAL_PER_G_PROTEIN = 4.0
KCAL_PER_G_CARB = 4.0
KCAL_PER_G_FAT = 9.0

# CONVENTION. Protein scales with body weight, not with the calorie target --
# that is the whole reason this app does not use a fixed percentage split. 1.8
# g/kg sits inside the range usually recommended for someone in a deficit
# trying to keep muscle; 1.6-2.2 would all be defensible. Fat then takes a
# quarter of calories (20-35% is the usual band) and carbohydrate is whatever
# is left, because carbohydrate is the macro with no established minimum.
PROTEIN_G_PER_KG = 1.8
FAT_FRACTION_OF_CALORIES = 0.25

# POLICY. Refusals, not science. The rate cap stops a typo like "-5" becoming a
# starvation target; the two floors stop an aggressive but legal rate doing the
# same thing more slowly. The absolute floors are the commonly cited "do not go
# below without supervision" numbers; the fractional floor is ours, and exists
# because a floor in absolute kcal is far too permissive for a large person.
MAX_GOAL_RATE_KG_PER_WEEK = 1.0
MIN_TARGET_KCAL = {"male": 1500.0, "female": 1200.0}
MIN_TARGET_FRACTION_OF_TDEE = 0.75

# POLICY. How much logging is enough before an energy-balance TDEE is allowed to
# drive a target. All three are refusals, chosen against real data rather than
# picked round: on a genuinely dense fortnight (24/24 logged days, 23 weigh-ins)
# a 7-day window produced 2700 kcal against 2498 from the formula, because trend
# weight had moved -0.01 kg over 6 days and dividing 7700 kcal/kg by that much
# noise amplifies it. Every window of 10 days or more landed within 2-4% of the
# formula. 14 is where the number stopped moving.
#
# The span is measured between the first and last weigh-in *inclusive*, not from
# the window's nominal width -- what matters is the period the slope was
# actually fitted over.
TDEE_MIN_SPAN_DAYS = 14
TDEE_MIN_LOGGED_DAYS = 10
TDEE_MIN_WEIGH_INS = 10

# POLICY. And how much of the measured period has to be logged, as a fraction.
# The mean intake stands in for every day in the span, including the unlogged
# ones, so this bounds how far that extrapolation is allowed to reach. The
# absolute floor above binds at the shortest allowed span; this one binds as
# the span grows, which is where a 10-of-28-days average would otherwise start
# describing mostly days nobody recorded.
TDEE_MIN_LOGGED_FRACTION = 0.7

# POLICY. The band a measured TDEE has to land in to be believable, as a
# multiple of the same person's BMR. The lower bound is the one that matters:
# nobody expends less than they would lying still, so a measured value beneath
# it is proof the inputs are wrong -- almost always meals that were eaten and
# not logged -- rather than a discovery about their metabolism. The upper bound
# catches the mirror error (a mistyped weigh-in inventing a large loss).
TDEE_PLAUSIBLE_BMR_RANGE = (1.1, 2.5)


class TargetCalories(NamedTuple):
    """A calorie target, and why it is not the one the rate asked for.

    `clamped_reason` is None when the target is exactly what the requested rate
    implies. When it is set, the UI is expected to show it: a target that
    silently disagrees with the rate the user typed is worse than no target,
    because the user goes on believing the rate.
    """

    calories: float
    clamped_reason: str | None


def age_years(birth_date: date_type, on: date_type | None = None) -> int:
    """Whole years old, on `on` (default today).

    The birthday itself counts as the new age. Stored as a date rather than a
    number precisely so this can be recomputed instead of going stale.
    """
    today = on or date_type.today()
    had_birthday = (today.month, today.day) >= (birth_date.month, birth_date.day)
    return today.year - birth_date.year - (0 if had_birthday else 1)


def bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    """Body mass index in kg/m², or None if either input is missing.

    Returns None rather than raising because both inputs are optional profile
    fields: "we don't know yet" is an ordinary state here, not an error.
    """
    if not weight_kg or not height_cm:
        return None
    height_m = height_cm / 100
    return round(weight_kg / (height_m * height_m), 1)


def bmr_mifflin_st_jeor(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
    sex_offset: dict[str, float] = MIFFLIN_SEX_OFFSET,
) -> float:
    """Resting energy expenditure, in kcal/day, by Mifflin-St Jeor.

    Takes a binary sex term because the published equation does. That is a
    limitation of the formula rather than a claim about people, which is why
    the field is optional in the UI and why Phase 5's measured TDEE is intended
    to replace this entirely rather than refine it.
    """
    if sex not in sex_offset:
        raise ValueError(f"unknown sex: {sex!r}")
    if weight_kg <= 0 or height_cm <= 0:
        raise ValueError("weight and height must be greater than zero")

    return round(
        MIFFLIN_WEIGHT_COEFFICIENT * weight_kg
        + MIFFLIN_HEIGHT_COEFFICIENT * height_cm
        - MIFFLIN_AGE_COEFFICIENT * age
        + sex_offset[sex],
        1,
    )


def activity_multiplier(
    level: str, multipliers: dict[str, float] = ACTIVITY_MULTIPLIERS
) -> float:
    """The chosen multiplier for an activity level. Raises on an unknown one.

    Raising rather than defaulting to sedentary: a silent fallback would make a
    typo in a stored level read as a real, plausible, wrong TDEE.
    """
    if level not in multipliers:
        raise ValueError(f"unknown activity level: {level!r}")
    return multipliers[level]


def estimated_tdee(
    weight_kg: float, height_cm: float, age: int, sex: str, activity_level: str
) -> float:
    """Total daily energy expenditure, estimated from the profile alone.

    "Estimated" is load-bearing: this is a formula applied to five numbers the
    user typed, and it can be out by several hundred kcal for an individual.
    Phase 5 measures the same quantity from logged intake and weight change,
    and that number supersedes this one wherever both exist.
    """
    bmr = bmr_mifflin_st_jeor(weight_kg, height_cm, age, sex)
    return round(bmr * activity_multiplier(activity_level), 1)


def measured_tdee(
    mean_daily_intake: float,
    weekly_rate_kg: float,
    kcal_per_kg: float = KCAL_PER_KG,
) -> float:
    """Total daily energy expenditure, measured from this person's own data.

    Energy balance, and nothing more: what you ate, minus what your body banked
    as tissue, is what you burned. Both inputs must describe the **same days** --
    a mean intake over one period and a weight slope over another is not an
    energy balance, it is two unrelated numbers subtracted. `RATE_WINDOW_DAYS`
    is what keeps them aligned; see `targets.py`.

    Unlike `estimated_tdee` this needs no height, age, sex or activity guess. It
    observes the individual instead of predicting them from a population, which
    is the whole point: the activity multiplier is the roughest step in the
    formula chain and this replaces it outright rather than tuning it.

    Note for Phase 7 (steps): the number returned here **already contains** the
    energy spent on every step taken during the measurement window. Adding a
    step-derived burn on top of it double-counts, and would tell the user to eat
    several hundred kcal more than they should. Steps may feed `estimated_tdee`,
    never this.
    """
    stored_kcal_per_day = (weekly_rate_kg / 7.0) * kcal_per_kg
    return round(mean_daily_intake - stored_kcal_per_day, 1)


class PlausibleTDEE(NamedTuple):
    """A measured TDEE, and why it is not the number the data implied.

    Same shape and same contract as `TargetCalories`: when `clamped_reason` is
    set the UI is expected to show it, because a silently corrected number
    leaves the user believing inputs that are actually wrong.
    """

    calories: float
    clamped_reason: str | None


def clamp_measured_tdee(
    tdee: float,
    bmr: float,
    bounds: tuple[float, float] = TDEE_PLAUSIBLE_BMR_RANGE,
) -> PlausibleTDEE:
    """Hold a measured TDEE inside a believable band around the person's BMR.

    This is the guard that matters most, and the reason it cannot be left to
    `target_calories`'s existing floor is worth stating plainly: that floor is
    computed as a fraction *of the TDEE itself*, so a TDEE dragged down by
    unlogged meals drags its own safety floor down with it and the check passes.
    Anchoring to BMR instead brings in a quantity that under-logging cannot
    move, because it is derived from body measurements rather than from intake.
    """
    low, high = bounds
    floor, ceiling = bmr * low, bmr * high

    if tdee < floor:
        return PlausibleTDEE(
            calories=float(round(floor)),
            clamped_reason=(
                f"Your logged intake works out to {round(tdee):g} kcal a day "
                f"burned, which is below what your body uses at rest — that is "
                f"not possible, and it usually means some meals aren't being "
                f"logged. Using {round(floor):g} kcal until the logs catch up."
            ),
        )
    if tdee > ceiling:
        return PlausibleTDEE(
            calories=float(round(ceiling)),
            clamped_reason=(
                f"Your logs work out to {round(tdee):g} kcal a day burned, which "
                f"is higher than this calculation can credibly explain — usually "
                f"a mistyped weigh-in. Using {round(ceiling):g} kcal instead."
            ),
        )
    return PlausibleTDEE(calories=float(round(tdee)), clamped_reason=None)


def target_calories(
    tdee: float,
    goal_rate_kg_per_week: float,
    sex: str,
    max_rate: float = MAX_GOAL_RATE_KG_PER_WEEK,
    min_kcal: dict[str, float] = MIN_TARGET_KCAL,
    min_fraction: float = MIN_TARGET_FRACTION_OF_TDEE,
) -> TargetCalories:
    """Daily calories for a requested rate of weight change, with safety clamps.

    Two independent clamps apply, and both report themselves. The rate cap
    catches an implausible request outright; the floor catches a request that
    is individually legal but lands somewhere nobody should eat. Both can fire
    at once, in which case both are reported -- the user asked for a rate and
    got neither it nor the target it implies, and needs to know that twice over.
    """
    reasons: list[str] = []

    rate = goal_rate_kg_per_week
    if abs(rate) > max_rate:
        rate = max_rate if rate > 0 else -max_rate
        reasons.append(
            f"Rate limited to {max_rate:g} kg/week (you asked for "
            f"{goal_rate_kg_per_week:g})."
        )

    calories = tdee + (rate * KCAL_PER_KG) / 7
    floor = max(min_kcal.get(sex, min(min_kcal.values())), tdee * min_fraction)
    if calories < floor:
        reasons.append(
            f"Raised to {round(floor):g} kcal — the floor for your estimated "
            f"expenditure. Losing faster than this needs medical supervision."
        )
        calories = floor

    return TargetCalories(
        # Whole kcal. Anything finer is false precision on a number built from
        # a formula with a several-hundred-kcal error bar.
        calories=float(round(calories)),
        clamped_reason=" ".join(reasons) if reasons else None,
    )


def macro_targets(
    calories: float,
    weight_kg: float,
    protein_g_per_kg: float = PROTEIN_G_PER_KG,
    fat_fraction: float = FAT_FRACTION_OF_CALORIES,
) -> dict[str, float]:
    """Split a calorie target into protein / carbs / fat, in whole grams.

    Protein comes off body weight and fat off total calories, so carbohydrate
    absorbs the remainder. That ordering is the point: a fixed percentage split
    would make protein *fall* as the calorie target falls, which is backwards
    during a cut, when protein matters most and calories least.

    Carbohydrate floors at zero. At a very low target, protein and fat alone
    can exceed the budget -- the split then no longer sums to `calories`, and
    the caller should treat that as the sign it is, not paper over it.
    """
    protein_g = protein_g_per_kg * weight_kg
    fat_g = (fat_fraction * calories) / KCAL_PER_G_FAT
    remaining = calories - protein_g * KCAL_PER_G_PROTEIN - fat_g * KCAL_PER_G_FAT
    carbs_g = max(remaining / KCAL_PER_G_CARB, 0.0)

    # Whole grams, for the same reason calories are whole: the inputs do not
    # support a decimal place.
    return {
        "protein": float(round(protein_g)),
        "carbs": float(round(carbs_g)),
        "fat": float(round(fat_g)),
    }


# CONVENTION. Millilitres of water per kilogram of body weight per day. The
# guidance usually quoted is 30-35 ml/kg; 35 is the top of that band, chosen
# because the failure modes are not symmetric -- a goal slightly too high is a
# glass of water, a goal too low is a tracker that says "done" before you are.
# Nothing about this is measured, it varies with climate, activity and diet,
# and it is why the UI shows the arithmetic next to the answer rather than the
# answer alone.
WATER_ML_PER_KG = 35.0

# CONVENTION. What to show when there is no weigh-in to derive from. 2 litres
# is the folk figure, which is exactly why it is the fallback and not the
# formula: it is a reasonable default for an unknown adult and a poor one for
# any specific adult. `WaterGoalBasis.source` says when this is being used, so
# the UI can ask for a weigh-in instead of quietly presenting it as personal.
WATER_DEFAULT_GOAL_ML = 2000.0

# CONVENTION. The quick-add amounts a new account starts with: a glass, a large
# glass, and a small bottle. Settable per user, so this is only a starting
# point. A tuple, not a list, so nothing can mutate the shipped default.
DEFAULT_WATER_QUICK_ADDS = (250.0, 500.0, 750.0)


class WaterGoal(NamedTuple):
    """A daily water goal, and where the number came from.

    `source` is what the UI renders the explanation from -- the standing rule
    that no derived number reaches the screen without its inputs beside it. The
    three cases genuinely differ: "custom" is the user's own figure and needs no
    justification, "weight" has arithmetic worth showing, and "default" is a
    stand-in that should invite a weigh-in rather than look personal.
    """

    ml: float
    source: str  # "custom" | "weight" | "default"
    ml_per_kg: float | None
    weight_kg: float | None


def water_goal(
    weight_kg: float | None,
    custom_ml: float | None = None,
    ml_per_kg: float = WATER_ML_PER_KG,
) -> WaterGoal:
    """Resolve the daily water goal from the user's own figure or their weight.

    A stored `custom_ml` always wins: the user overrode the derivation on
    purpose, and a goal that silently drifted with their weight after they set
    it by hand would be the app overruling them.

    Deliberately takes the *smoothed* trend weight rather than the latest
    reading, because that is the app's single definition of what someone
    weighs -- and because a goal that jumped every time the scale caught a
    litre of yesterday's water would be circular in a way that is almost funny.
    """
    if custom_ml is not None:
        return WaterGoal(
            ml=float(custom_ml), source="custom", ml_per_kg=None, weight_kg=None
        )
    if weight_kg is None:
        return WaterGoal(
            ml=WATER_DEFAULT_GOAL_ML,
            source="default",
            ml_per_kg=None,
            weight_kg=None,
        )
    # Rounded to 50 ml. The inputs do not support finer than that, and
    # "2,447 ml" reads as a measurement of something rather than as the rule of
    # thumb it is.
    ml = round(ml_per_kg * weight_kg / 50.0) * 50.0
    return WaterGoal(
        ml=float(ml), source="weight", ml_per_kg=ml_per_kg, weight_kg=weight_kg
    )
