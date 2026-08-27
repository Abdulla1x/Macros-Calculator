"""The weekly review: one page of what the app already knows.

Every number here was computed somewhere else already -- `targets.py` for the
burn and the clamps, `calculations.py` for the weight trend, `calibration.py`
for the estimate accuracy, and the meals table for the rest. What did not exist
was a place where they sit together, which is the whole feature.

All the arithmetic and every sentence live in `app/review.py`, which is pure.
This file is the database and HTTP around them, the same split
`routers/plan.py` keeps with `banking.py`.

**Nothing here writes.** It is a read-only summary and it spends no AI quota:
the calibration line reuses rows that each already represent a billable call,
and the optional rephrasing is a separate, explicitly-requested endpoint in
`routers/ai.py`.
"""
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import review as review_module
from ..auth.deps import get_current_user
from ..calculations import (
    RATE_MIN_POINTS,
    RATE_WINDOW_DAYS,
    water_goal,
    weekly_rate,
    weight_trend,
)
from ..db import get_db
from ..models import CaloriePlanDay, Meal, Setting, StepEntry, User, WaterLog, WeightEntry
from ..review import REVIEW_WINDOW_DAYS, DayIntake, TargetsFacts
from ..schemas import WeeklyReview
from ..targets import WEIGHT_LOOKBACK_DAYS, _latest_trend_weight, compute_targets
from .ai import calibration_summary
from .settings import _get_or_create

router = APIRouter(prefix="/api/review", tags=["review"])


def _intake_days(
    db: Session, user_id: int, start: date_type, end: date_type
) -> list[DayIntake]:
    """One row per day that has any meal on it, calories and protein summed.

    Days with nothing logged are absent rather than zero, which is the
    denominator `routers/analytics.py` argues for at length: an unlogged day
    means "did not log", never "ate nothing", and counting it as zero would
    report someone as eating hundreds of kcal less than they did.
    """
    rows = db.execute(
        select(
            Meal.date,
            func.sum(Meal.calories),
            func.sum(Meal.protein),
        )
        .where(Meal.user_id == user_id, Meal.date >= start, Meal.date <= end)
        .group_by(Meal.date)
        .order_by(Meal.date)
    ).all()
    return [
        DayIntake(day, float(calories or 0.0), float(protein or 0.0))
        for day, calories, protein in rows
    ]


def _daily_calorie_target(
    db: Session, user_id: int, setting: Setting, days: list[DayIntake]
) -> tuple[float, bool]:
    """The mean target actually in force across the days that were logged.

    Not `setting.calorie_goal`: a calorie plan moves individual days, and
    `routers/plan.py` states the rule -- the stored goal is what is saved, the
    composed one is what a ring is drawn against. Telling someone they went 400
    kcal over on a day they deliberately planned for would be this feature's
    first wrong answer.

    ⚠️ Averaged over **the logged days**, not over the seven-day window, so that
    both halves of the comparison describe the same days. `targets._measure_tdee`
    makes exactly this alignment argument about intake and the weight slope: a
    mean over one set of days minus a mean over another is not a comparison.

    Worth knowing before reading a target that looks untouched: a *planned*
    group's deltas sum to zero, so once one sits wholly inside the window the
    mean comes out at exactly the stored goal even though four days moved. That
    state is unreachable at the moment a plan is written -- `validate_plan`
    only adjusts today or later, and this window ends yesterday -- so it
    arrives purely with the passage of time, which is also why no test can
    construct it through the API. `plan_touched` is what keeps it visible.
    """
    if not days:
        return float(setting.calorie_goal), False

    deltas = dict(
        db.execute(
            select(CaloriePlanDay.date, CaloriePlanDay.calorie_delta).where(
                CaloriePlanDay.user_id == user_id,
                CaloriePlanDay.date >= days[0].date,
                CaloriePlanDay.date <= days[-1].date,
            )
        ).all()
    )
    per_day = [float(setting.calorie_goal) + float(deltas.get(day.date, 0.0)) for day in days]
    # True only when a plan touched a day that was actually logged -- a plan on
    # a day with no meals moved no comparison, so mentioning it would explain a
    # difference the reader cannot see.
    touched = any(deltas.get(day.date) for day in days)
    return sum(per_day) / len(per_day), touched


def _weight_facts(
    db: Session, user_id: int, end: date_type
) -> tuple[float | None, int, int | None]:
    """`(weekly rate, weigh-ins in the rate window, days since the last one)`.

    Computed exactly the way `routers/weights.py` computes it, seeded from the
    same 90-day lookback, so the review and the Weight page cannot print two
    different rates for the same account. Nothing is recomputed here that
    `calculations.py` already defines.

    Clipped to `end` rather than to today, because the review describes a window
    that closed yesterday and a weigh-in logged this morning is not part of it.
    """
    rows = db.scalars(
        select(WeightEntry)
        .where(
            WeightEntry.user_id == user_id,
            WeightEntry.date >= end - timedelta(days=WEIGHT_LOOKBACK_DAYS - 1),
            WeightEntry.date <= end,
        )
        .order_by(WeightEntry.date)
    ).all()
    points = weight_trend([(row.date, row.weight_kg) for row in rows])
    if not points:
        return None, 0, None

    latest = points[-1].date
    cutoff = latest - timedelta(days=RATE_WINDOW_DAYS - 1)
    in_window = sum(1 for point in points if point.date >= cutoff)
    return weekly_rate(points), in_window, (end - latest).days


def _water_days_at_goal(
    db: Session, user_id: int, setting: Setting, start: date_type, end: date_type
) -> int | None:
    """Days the water goal was reached, or None if this account never uses water.

    ⚠️ The opt-in test is "has ever logged water", **not** "logged water this
    week". `water_goal_ml` NULL means "derive it from my weight" rather than
    "off" (`models.py`), so unlike steps there is no column carrying the
    answer -- and a window-scoped test would hide the section from someone who
    does track water and had a bad week, which is the week worth reading.
    """
    ever = db.scalar(
        select(WaterLog.id).where(WaterLog.user_id == user_id).limit(1)
    )
    if ever is None:
        return None

    # Only look up a weight when one is actually needed, exactly as
    # routers/water.py does: a custom goal costs no extra query.
    weight_kg = None
    if setting.water_goal_ml is None:
        weight = _latest_trend_weight(db, user_id)
        weight_kg = weight[0] if weight is not None else None
    goal = water_goal(weight_kg, setting.water_goal_ml)
    totals = db.execute(
        select(WaterLog.date, func.sum(WaterLog.ml))
        .where(WaterLog.user_id == user_id, WaterLog.date >= start, WaterLog.date <= end)
        .group_by(WaterLog.date)
    ).all()
    return sum(1 for _, total in totals if float(total or 0.0) >= goal.ml)


def _steps_days_at_goal(
    db: Session, user_id: int, goal: int, start: date_type, end: date_type
) -> int:
    """Days the step goal was reached. One row per date, replaced on re-save."""
    return (
        db.scalar(
            select(func.count())
            .select_from(StepEntry)
            .where(
                StepEntry.user_id == user_id,
                StepEntry.date >= start,
                StepEntry.date <= end,
                StepEntry.steps >= goal,
            )
        )
        or 0
    )


@router.get("", response_model=WeeklyReview)
def weekly_review(
    end: date_type | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The last seven complete days, and what can honestly be said about them.

    `end` is the last day the review covers and the client sends **its own**
    local yesterday, following `/api/analytics/daily` and `/api/plan/day`. No
    timezone is stored for anyone and the server's `date.today()` is UTC, so a
    server-computed "yesterday" is wrong for everyone hours off it -- the Phase
    19 finding, applied before it could bite again.

    The window ends yesterday because today is a part-logged day: averaging
    breakfast-only into a daily mean understates intake and would make every
    review read as a better week than it was.

    Read-only, always 200. An account with nothing logged is an ordinary state
    and the refusals are the answer, each naming what is still missing.
    """
    today = date_type.today()
    window_end = end if end is not None else today - timedelta(days=1)
    if window_end > today:
        # A future window would report on days that have not happened. Refusing
        # is better than silently clamping: a client asking for tomorrow has a
        # bug, and quietly answering about yesterday hides it.
        raise HTTPException(status_code=422, detail="end must not be in the future")
    window_start = window_end - timedelta(days=REVIEW_WINDOW_DAYS - 1)

    setting = _get_or_create(db, user.id)
    days = _intake_days(db, user.id, window_start, window_end)
    daily_target, plan_touched = _daily_calorie_target(db, user.id, setting, days)
    rate, weigh_ins, days_since = _weight_facts(db, user.id, window_end)

    # `today` for the target machinery is the day after the window closes, so
    # its own measurement window ends where this review's does. Passing the real
    # today would let a meal logged this morning move a figure in a review that
    # deliberately stops at yesterday.
    targets = compute_targets(db, setting, today=window_end + timedelta(days=1))
    basis = targets.tdee_basis

    steps_goal = setting.steps_goal
    return review_module.summarise(
        window_start=window_start,
        window_end=window_end,
        days=days,
        daily_calorie_target=daily_target,
        protein_goal=float(setting.protein_goal),
        plan_touched=plan_touched,
        targets=TargetsFacts(
            missing=tuple(targets.missing),
            tdee=targets.tdee,
            tdee_source=targets.tdee_source,
            logged_days=basis.logged_days if basis else 0,
            weigh_ins=basis.weigh_ins if basis else 0,
            span_days=basis.span_days if basis else 0,
            basis_reason=basis.unavailable_reason if basis else None,
            clamped_reason=targets.clamped_reason,
        ),
        rate_kg=rate,
        goal_rate_kg=setting.goal_rate_kg_per_week,
        weigh_ins=weigh_ins,
        days_since_weigh_in=days_since,
        water_days_at_goal=_water_days_at_goal(
            db, user.id, setting, window_start, window_end
        ),
        steps_days_at_goal=(
            None
            if steps_goal is None
            else _steps_days_at_goal(db, user.id, steps_goal, window_start, window_end)
        ),
        steps_goal=steps_goal,
        calibration=calibration_summary(db, user.id),
        rate_window_days=RATE_WINDOW_DAYS,
        rate_min_points=RATE_MIN_POINTS,
    )
