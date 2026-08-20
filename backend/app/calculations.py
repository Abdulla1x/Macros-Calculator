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
