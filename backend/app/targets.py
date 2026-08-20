"""Turning a body profile into daily targets.

One module, isolated the way `services/meal_ai.py` isolates the AI provider,
and for the same reason: **this is the only file that knows how a target is
derived.** The measured TDEE landed here as planned -- `compute_targets` now
measures energy balance where it used to apply a formula, and the router, the
settings columns, `apply_auto_targets` and the four goal columns did not move.

One prediction did not survive contact, and it is worth recording rather than
quietly correcting. The plan said the frontend would not change either. It had
to: the Settings card told the user in plain words that these numbers were
"Estimates, not measurements -- a formula applied to what you typed above", and
a measured number behind that sentence makes the app assert something false. A
swap that is invisible in the code is not automatically invisible on screen.

The arithmetic itself lives in `calculations.py` and stays pure. This module is
the part that knows about the database.
"""
from dataclasses import dataclass
from datetime import date as date_type
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .calculations import (
    RATE_WINDOW_DAYS,
    TDEE_MIN_LOGGED_DAYS,
    TDEE_MIN_LOGGED_FRACTION,
    TDEE_MIN_SPAN_DAYS,
    TDEE_MIN_WEIGH_INS,
    age_years,
    bmi,
    bmr_mifflin_st_jeor,
    clamp_measured_tdee,
    estimated_tdee,
    macro_targets,
    measured_tdee,
    target_calories,
    weekly_rate,
    weight_trend,
)
from .models import Meal, Setting, WeightEntry

# How far back to look for a weigh-in. A profile without a recent weight cannot
# produce a target: deriving today's calories from a number three months old is
# exactly the kind of confident-looking wrong answer this app exists not to
# give. 90 days also matches the Weight page's default chart window, so what
# feeds the target is what the user can already see.
WEIGHT_LOOKBACK_DAYS = 90

# The floor a written-back goal is allowed to take. `schemas.Settings` requires
# all four goals to be strictly positive, and that schema is the *response*
# model as well as the request one -- so storing a computed 0 would not fail
# loudly at write time, it would turn every later GET /api/settings into a 500
# and lock the user out of their own settings page. `macro_targets` floors
# carbohydrate at zero by design, and a small enough body weight rounds protein
# to zero too, so this is reachable rather than theoretical. Same shape as the
# lesson in Phase 3: rejecting a value can be more dangerous than accepting it.
MIN_WRITTEN_GOAL = 1.0


@dataclass(frozen=True)
class TdeeBasis:
    """What the measured TDEE was built from -- or what it is still short of.

    Always populated once the profile is complete, whether or not measurement
    succeeded, because "you are 6 weigh-ins away from a measured number" is a
    far more useful thing to show than a bare estimate that never explains
    itself. `unavailable_reason` is None exactly when the measurement was used.

    The counts are here for the same reason `weight_kg` and `weight_date` are on
    TargetsResult: no derived number reaches the UI without the inputs it came
    from visible beside it, and a TDEE's sample size is the input most likely to
    be quietly too small.
    """

    logged_days: int
    weigh_ins: int
    span_days: int
    mean_intake: float | None = None
    trend_change_kg: float | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class TargetsResult:
    """Everything derived from the profile, plus what stopped it being derived.

    `missing` is the machine-readable half: an empty list means every number
    below is populated, and a non-empty one names the profile fields that are
    absent, so the UI can say "add your height" instead of showing a blank card
    with no explanation.

    `weight_kg` and `weight_date` travel together on purpose. The standing
    ground rule is that no derived number reaches the UI without its inputs
    visible beside it, and body weight is the input most likely to be quietly
    stale.
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
    clamped_reason: str | None = None
    # "measured" once energy balance drove the number, "estimated" while the
    # formula is still doing it. Declared here and not only on `schemas.
    # BodyTargets` on purpose: FastAPI converts this dataclass with
    # `dataclasses.asdict` before validating it against the response model, so a
    # field the schema declares and this class omits does not fail loudly -- it
    # silently serialises as the schema's default. That is the same trap that
    # demoted every admin in Phase 2 and emptied every template in Phase 3.
    tdee_source: str = "estimated"
    # The formula number, kept even when measurement won, so the card can show
    # the two side by side. They agreeing is reassuring; them diverging is the
    # signal that something is wrong with the logs.
    tdee_estimated: float | None = None
    tdee_basis: TdeeBasis | None = None

    @property
    def available(self) -> bool:
        return not self.missing


def _latest_trend_weight(
    db: Session, user_id: int, today: date_type | None = None
) -> tuple[float, date_type] | None:
    """The user's most recent smoothed weight, or None if there isn't one.

    Smoothed, not raw: `weight_trend` is already the app's single definition of
    "what this person weighs", and a target that moved with every water-weight
    swing would be noise dressed up as coaching.
    """
    cutoff = (today or date_type.today()) - timedelta(days=WEIGHT_LOOKBACK_DAYS - 1)
    rows = db.scalars(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id, WeightEntry.date >= cutoff)
        .order_by(WeightEntry.date)
    ).all()
    if not rows:
        return None

    points = weight_trend([(row.date, row.weight_kg) for row in rows])
    return points[-1].trend_kg, points[-1].date


def _measure_tdee(
    db: Session, user_id: int, bmr: float, today: date_type
) -> tuple[float | None, str | None, TdeeBasis]:
    """TDEE from this person's own energy balance, or None and the reason why not.

    Returns `(tdee, clamped_reason, basis)`. A None tdee is an ordinary answer,
    not an error: most accounts weigh in far too rarely for this to be
    answerable, so the formula fallback is the common path rather than the edge
    case.

    **Two alignment decisions carry this function, and both are load-bearing.**

    *The window ends yesterday, never today.* Today is a partly-logged day --
    breakfast is in, dinner is not -- and averaging it in as though it were a
    finished day understates intake, which understates expenditure, which tells
    the user to eat less. Measured on real data, including today moved a 14-day
    TDEE from 2589 to 2366 kcal. This is the Phase 0.6 dashboard bug in a new
    place, and it bites harder here because the answer feeds a target rather
    than a chart. It also removes a feedback loop for free: today's meals cannot
    move today's target, so eating more cannot raise the goal you are eating
    towards.

    *Intake is averaged over exactly the days the weight slope was fitted over.*
    An energy balance subtracts two quantities describing the same period; a
    mean intake over 28 days minus a slope over 12 is not a balance, it is two
    unrelated numbers. So the span comes from the weigh-ins, and the intake
    query is then clipped to it.
    """
    window_end = today - timedelta(days=1)
    window_start = window_end - timedelta(days=RATE_WINDOW_DAYS - 1)

    # Smoothing is seeded from the full lookback and only then clipped to the
    # window. Seeding it from the window's own first entry would start the EWMA
    # at a raw weigh-in and let one noisy morning tilt the whole fit.
    lookback_start = today - timedelta(days=WEIGHT_LOOKBACK_DAYS - 1)
    rows = db.scalars(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id, WeightEntry.date >= lookback_start)
        .order_by(WeightEntry.date)
    ).all()
    points = [
        point
        for point in weight_trend([(row.date, row.weight_kg) for row in rows])
        if window_start <= point.date <= window_end
    ]

    weigh_ins = len(points)
    span_days = (points[-1].date - points[0].date).days + 1 if weigh_ins >= 2 else weigh_ins

    # Fetched once, for the whole window, and narrowed in Python afterwards.
    # Doing it here rather than after the weigh-in guards is what stops a
    # refusal reporting `logged_days: 0` at someone who has logged every day
    # for three weeks -- the guard that fired was about weigh-ins, and a count
    # that is wrong in the payload is wrong whether or not the card draws it.
    intake_by_day = dict(
        db.execute(
            select(Meal.date, func.sum(Meal.calories))
            .where(
                Meal.user_id == user_id,
                Meal.date >= window_start,
                Meal.date <= window_end,
            )
            .group_by(Meal.date)
        ).all()
    )

    def unavailable(reason: str, logged_days: int | None = None) -> tuple[None, None, TdeeBasis]:
        return None, None, TdeeBasis(
            logged_days=len(intake_by_day) if logged_days is None else logged_days,
            weigh_ins=weigh_ins,
            span_days=span_days,
            unavailable_reason=reason,
        )

    if weigh_ins < TDEE_MIN_WEIGH_INS:
        return unavailable(
            f"Weigh in on {TDEE_MIN_WEIGH_INS - weigh_ins} more days and your "
            f"calorie burn can be measured from your own data instead of "
            f"estimated from a formula."
        )
    if span_days < TDEE_MIN_SPAN_DAYS:
        return unavailable(
            f"Your weigh-ins so far cover {span_days} days. Measuring needs at "
            f"least {TDEE_MIN_SPAN_DAYS} days between the first and last one — "
            f"below that, normal day-to-day weight swings swamp the trend."
        )

    # Narrowed to the weigh-in span, per the docstring: the mean intake and the
    # weight slope have to describe the same days to be an energy balance.
    first_day, last_day = points[0].date, points[-1].date
    in_span = {
        day: total
        for day, total in intake_by_day.items()
        if first_day <= day <= last_day
    }
    logged_days = len(in_span)

    # Per *logged* day, the same denominator analytics.py settled on: an
    # unlogged day means "did not log", never "ate nothing", and counting it as
    # zero would understate intake and so understate the measured burn.
    required_days = max(
        TDEE_MIN_LOGGED_DAYS, round(TDEE_MIN_LOGGED_FRACTION * span_days)
    )
    if logged_days < required_days:
        return unavailable(
            f"You logged meals on {logged_days} of the last {span_days} days. "
            f"Measuring needs {required_days} — the average stands in for the "
            f"days you did not log, so too few of them makes it a guess.",
            logged_days=logged_days,
        )

    mean_intake = sum(float(total) for total in in_span.values()) / logged_days
    rate = weekly_rate(
        points, window_days=RATE_WINDOW_DAYS, min_points=TDEE_MIN_WEIGH_INS
    )
    if rate is None:
        return unavailable(
            "Your weigh-ins do not yet spread across enough days to fit a "
            "trend through.",
            logged_days=logged_days,
        )

    plausible = clamp_measured_tdee(measured_tdee(mean_intake, rate), bmr)
    return (
        plausible.calories,
        plausible.clamped_reason,
        TdeeBasis(
            logged_days=logged_days,
            weigh_ins=weigh_ins,
            span_days=span_days,
            mean_intake=round(mean_intake, 1),
            trend_change_kg=round(points[-1].trend_kg - points[0].trend_kg, 2),
        ),
    )


def compute_targets(
    db: Session, setting: Setting, today: date_type | None = None
) -> TargetsResult:
    """Derive BMI, BMR, TDEE, a calorie target and a macro split for one user.

    Reports what is missing rather than substituting a default for it. A
    plausible-looking target built on an assumed height is worse than no
    target, because nothing about it looks wrong.
    """
    weight = _latest_trend_weight(db, setting.user_id, today=today)
    weight_kg, weight_date = weight if weight is not None else (None, None)

    missing: list[str] = []
    if weight_kg is None:
        missing.append("weight")
    if not setting.height_cm:
        missing.append("height_cm")
    if setting.birth_date is None:
        missing.append("birth_date")
    if not setting.sex:
        missing.append("sex")
    if not setting.activity_level:
        missing.append("activity_level")
    # Maintenance is a rate of 0, which has to be chosen rather than inferred
    # from an empty field -- "unset" and "I want to maintain" are different
    # answers and only one of them is safe to act on.
    if setting.goal_rate_kg_per_week is None:
        missing.append("goal_rate_kg_per_week")

    # BMI needs only two of the six, so it is worth returning even when the
    # rest of the profile is incomplete -- it is the first number a new user
    # can see, from one weigh-in and a height.
    body_mass_index = bmi(weight_kg, setting.height_cm)

    if missing:
        return TargetsResult(
            missing=missing,
            bmi=body_mass_index,
            weight_kg=weight_kg,
            weight_date=weight_date,
        )

    age = age_years(setting.birth_date, on=today)
    bmr = bmr_mifflin_st_jeor(weight_kg, setting.height_cm, age, setting.sex)
    estimated = estimated_tdee(
        weight_kg, setting.height_cm, age, setting.sex, setting.activity_level
    )

    # Measure if the logs can support it, estimate if they cannot. Everything
    # downstream is unchanged -- it receives a better number through the same
    # argument, which is precisely why this swap is confined to one function.
    measured, measure_clamp, basis = _measure_tdee(
        db, setting.user_id, bmr, today or date_type.today()
    )
    tdee = measured if measured is not None else estimated
    tdee_source = "measured" if measured is not None else "estimated"

    target = target_calories(tdee, setting.goal_rate_kg_per_week, setting.sex)
    macros = macro_targets(target.calories, weight_kg)

    # Both clamps can fire at once and both are the user's business: one says
    # the burn was implausible, the other that the requested rate was. Joined
    # rather than prioritised, the way target_calories already joins its two.
    clamp_reasons = [r for r in (measure_clamp, target.clamped_reason) if r]

    return TargetsResult(
        missing=[],
        bmi=body_mass_index,
        # BMR travels alongside the TDEE it produced rather than being folded
        # invisibly into it: the multiplier is the least trustworthy step in
        # the chain, and showing both makes its size obvious.
        bmr=bmr,
        tdee=tdee,
        target_calories=target.calories,
        protein_g=macros["protein"],
        carbs_g=macros["carbs"],
        fat_g=macros["fat"],
        weight_kg=weight_kg,
        weight_date=weight_date,
        clamped_reason=" ".join(clamp_reasons) if clamp_reasons else None,
        tdee_source=tdee_source,
        tdee_estimated=estimated,
        tdee_basis=basis,
    )


def apply_auto_targets(
    setting: Setting, db: Session, today: date_type | None = None
) -> None:
    """Rewrite the four goal columns from the profile, if the user asked for it.

    A no-op unless `targets_auto` is on, and a no-op when the profile is
    incomplete: the flag stays set and starts working the moment the missing
    field is filled in, rather than being silently switched off behind the
    user's back.

    Deliberately does not commit. Both callers -- the settings PUT and the
    weigh-in upsert -- are already inside a transaction with more to write, and
    committing here would split one logical change across two.
    """
    if not setting.targets_auto:
        return

    result = compute_targets(db, setting, today=today)
    if not result.available:
        return

    setting.calorie_goal = max(result.target_calories, MIN_WRITTEN_GOAL)
    setting.protein_goal = max(result.protein_g, MIN_WRITTEN_GOAL)
    setting.carbs_goal = max(result.carbs_g, MIN_WRITTEN_GOAL)
    setting.fat_goal = max(result.fat_g, MIN_WRITTEN_GOAL)
