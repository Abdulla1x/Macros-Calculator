"""Turning a body profile into daily targets.

One module, isolated the way `services/meal_ai.py` isolates the AI provider,
and for the same reason: **this is the file Phase 5 edits.** Swapping the
formula-based `estimated_tdee` for a measured TDEE derived from logged intake
and weight change happens inside `compute_targets` and nowhere else -- the
router, the schema, the settings columns and every line of frontend code stay
exactly as they are.

The arithmetic itself lives in `calculations.py` and stays pure. This module is
the part that knows about the database.
"""
from dataclasses import dataclass
from datetime import date as date_type
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calculations import (
    age_years,
    bmi,
    bmr_mifflin_st_jeor,
    estimated_tdee,
    macro_targets,
    target_calories,
    weight_trend,
)
from .models import Setting, WeightEntry

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
    tdee = estimated_tdee(
        weight_kg, setting.height_cm, age, setting.sex, setting.activity_level
    )
    target = target_calories(tdee, setting.goal_rate_kg_per_week, setting.sex)
    macros = macro_targets(target.calories, weight_kg)

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
        clamped_reason=target.clamped_reason,
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
