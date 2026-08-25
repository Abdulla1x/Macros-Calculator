"""Calorie banking: moving a day's target without moving the week's.

Five verbs over `calorie_plan_days`. The arithmetic and every refusal live in
`app/banking.py`; this file is the database and HTTP around them.

**Nothing here may write the four goal columns.** That is the invariant, and it
is a different one from the note at the top of `routers/steps.py`. Steps may not
*read* calorie targets because a measured TDEE already contains the energy every
step spent. This router legitimately reads them -- it exists to report what a
day's target is -- and what it must never do is persist the answer. The moment a
plan is written back into `settings.calorie_goal`, the next weigh-in calls
`apply_auto_targets`, overwrites all four columns, and the plan is gone with no
trace that it ever applied. Adjustments are stored per-day and composed on top
at read time, which is also what makes cancelling a plan exact: there is nothing
to recompute, the rows simply stop being there.

The corollary, for anyone reading a ring: `calorie_goal` in `GET /api/settings`
is the *stored* goal and `GET /api/plan/day` is the effective one. They differ
on precisely the days a plan touches, and the second is the one to draw.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..banking import (
    KIND_PLANNED,
    DayGoals,
    PlanEntry,
    apply_delta,
    split_delta,
    validate_plan,
)
from ..db import get_db
from ..models import CaloriePlanDay, Meal, Setting, User
from ..schemas import CaloriePlan, CaloriePlanCreate, DaySurplus, PlanDay
from ..targets import compute_targets
from .settings import _get_or_create

router = APIRouter(prefix="/api/plan", tags=["plan"])

# Below this, a day landed on its target closely enough that spreading the
# difference is noise -- a plan of rows that each move nothing. POLICY, and a
# small one: it exists to stop an empty gesture being stored as a plan, not to
# say anything about how close to target is close enough.
MIN_SURPLUS_KCAL = 1.0


def _base_goals(setting: Setting) -> DayGoals:
    """The stored goals, before any plan is applied."""
    return DayGoals(
        calories=setting.calorie_goal,
        protein=setting.protein_goal,
        carbs=setting.carbs_goal,
        fat=setting.fat_goal,
    )


def _row(db: Session, user_id: int, day: date_type) -> CaloriePlanDay | None:
    """The one adjustment on a user's day, if any.

    At most one by the unique index, which is what lets every reader here take
    `.first()` without wondering what a second row would have meant.
    """
    return db.scalars(
        select(CaloriePlanDay).where(
            CaloriePlanDay.user_id == user_id, CaloriePlanDay.date == day
        )
    ).first()


def _plan_day(setting: Setting, day: date_type, row: CaloriePlanDay | None) -> PlanDay:
    """One day's effective targets, built by hand rather than from a row.

    Explicit construction on purpose: `PlanDay` has defaulted fields, and a
    from_attributes model with defaults is the trap this codebase has hit three
    times -- an attribute the row does not carry serialises as the default
    instead of failing. Nothing here is stored, so there is no row to read it
    from anyway.
    """
    goals = _base_goals(setting)
    if row is not None:
        goals = apply_delta(goals, row.calorie_delta)

    return PlanDay(
        date=day,
        calorie_goal=goals.calories,
        protein_goal=goals.protein,
        carbs_goal=goals.carbs,
        fat_goal=goals.fat,
        # None, not 0.0: an untouched day and a day a plan moves by nothing are
        # different facts, and only the second has anything to cancel.
        calorie_delta=None if row is None else row.calorie_delta,
        kind=None if row is None else row.kind,
        event_date=None if row is None else row.event_date,
    )


def _day_surplus(
    db: Session, setting: Setting, day: date_type
) -> DaySurplus:
    """How far a day ran from the target it actually had.

    Measured against the *effective* target, not the stored goal. A day that was
    itself a planned big one is on plan when it lands on its raised target, and
    reporting that as a 700 kcal surplus would invite a compensation for eating
    exactly what was arranged.
    """
    row = _row(db, setting.user_id, day)
    reference = _plan_day(setting, day, row).calorie_goal

    consumed, meals = db.execute(
        select(func.coalesce(func.sum(Meal.calories), 0.0), func.count(Meal.id))
        .where(Meal.user_id == setting.user_id, Meal.date == day)
    ).one()

    return DaySurplus(
        date=day,
        consumed_calories=float(consumed),
        reference_calories=reference,
        surplus_calories=float(consumed) - reference,
        meal_count=int(meals),
        calorie_delta=None if row is None else row.calorie_delta,
    )


def _plan_out(
    setting: Setting, rows: list[CaloriePlanDay], today: date_type
) -> CaloriePlan:
    """One group of rows as a plan. `rows` must share an event_date."""
    ordered = sorted(rows, key=lambda r: r.date)
    first = ordered[0]
    return CaloriePlan(
        event_date=first.event_date,
        kind=first.kind,
        created_at=first.created_at,
        days=[_plan_day(setting, r.date, r) for r in ordered],
        total_delta=sum(r.calorie_delta for r in ordered),
        # A plan every day of which has already happened still exists and is
        # still shown; what it no longer is, is cancellable.
        can_cancel=any(r.date >= today for r in ordered),
    )


@router.get("/day", response_model=PlanDay)
def get_plan_day(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The four targets one day is actually measured against.

    Always 200, never 404, following `GET /api/steps`: a day with no plan on it
    is the ordinary case and its answer is the stored goals with a null delta,
    not an error.
    """
    day = date or date_type.today()
    setting = _get_or_create(db, user.id)
    return _plan_day(setting, day, _row(db, user.id, day))


@router.get("/surplus", response_model=DaySurplus)
def get_day_surplus(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Where the compensate-after flow starts: how far a finished day ran over.

    Consumed and reference are returned separately rather than pre-subtracted so
    the screen can say what the comparison was made against. This app stores no
    historical target -- the four goal columns are rewritten on every weigh-in
    -- so the reference is today's, and the user is entitled to know that before
    acting on the difference.
    """
    return _day_surplus(db, _get_or_create(db, user.id), date or date_type.today())


@router.get("", response_model=list[CaloriePlan])
def list_plans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every plan with at least one day still ahead, newest event first.

    Selected in two steps rather than one: the first finds the plans that are
    still live, the second pulls all of their rows including the days already
    spent. A plan shown with half its days missing would read as a smaller plan
    than it is.
    """
    today = date_type.today()
    live = db.scalars(
        select(CaloriePlanDay.event_date)
        .where(CaloriePlanDay.user_id == user.id, CaloriePlanDay.date >= today)
        .distinct()
    ).all()
    if not live:
        return []

    rows = db.scalars(
        select(CaloriePlanDay).where(
            CaloriePlanDay.user_id == user.id,
            CaloriePlanDay.event_date.in_(live),
        )
    ).all()

    setting = _get_or_create(db, user.id)
    grouped: dict[date_type, list[CaloriePlanDay]] = {}
    for row in rows:
        grouped.setdefault(row.event_date, []).append(row)

    return [
        _plan_out(setting, grouped[event], today)
        for event in sorted(grouped, reverse=True)
    ]


@router.post("", response_model=CaloriePlan, status_code=201)
def create_plan(
    body: CaloriePlanCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move calories between days, or refuse and say why.

    The split is computed here, never accepted from the client, so the parts
    provably re-add to the whole -- which is what makes the sum rules in
    `banking` an equality rather than a hope.

    Refusals come back as one 422 carrying every reason at once. A plan is
    validated as a set, so returning the first problem alone would send the user
    round the loop once per bad day.
    """
    today = date_type.today()
    setting = _get_or_create(db, user.id)
    goals = _base_goals(setting)
    # For the proportional floor. None when the body profile is incomplete, and
    # `banking.check_floor` says so rather than skipping the check.
    tdee = compute_targets(db, setting, today=today).tdee

    entries, surplus = _entries_for(db, setting, body, today)

    # Overlap, before validation: a day already owned by another plan is a
    # different answer from a day that breaks a rule, and conflating them would
    # tell the user to spread wider when the fix is to cancel something.
    _refuse_overlap(db, user.id, entries)

    check = validate_plan(
        entries,
        kind=body.kind,
        event_date=body.event_date,
        today=today,
        goals=goals,
        sex=setting.sex,
        tdee=tdee,
        surplus_kcal=surplus,
    )
    if check.refusals:
        raise HTTPException(status_code=422, detail=" ".join(check.refusals))

    for entry in entries:
        db.add(
            CaloriePlanDay(
                user_id=user.id,
                date=entry.date,
                event_date=body.event_date,
                kind=body.kind,
                calorie_delta=entry.calorie_delta,
            )
        )
    db.commit()

    rows = db.scalars(
        select(CaloriePlanDay).where(
            CaloriePlanDay.user_id == user.id,
            CaloriePlanDay.event_date == body.event_date,
        )
    ).all()
    return _plan_out(setting, list(rows), today)


def _entries_for(
    db: Session, setting: Setting, body: CaloriePlanCreate, today: date_type
) -> tuple[list[PlanEntry], float | None]:
    """Turn a request into the rows it asks for, and the surplus it spreads.

    The two kinds diverge here and nowhere else, which is deliberate: past this
    function everything downstream sees the same list of dated deltas.
    """
    if body.kind == KIND_PLANNED:
        if body.calorie_delta is None:
            raise HTTPException(
                status_code=422,
                detail="Say how many calories to move onto the day being planned.",
            )
        # The event day is itself adjusted, so it is one of the rows, and the
        # days named fund it. Signed: a negative delta is a deliberately small
        # day whose savings the others take on.
        funding = split_delta(-body.calorie_delta, len(body.dates))
        entries = [PlanEntry(body.event_date, float(body.calorie_delta))]
        entries += [PlanEntry(d, part) for d, part in zip(body.dates, funding)]
        return entries, None

    # KIND_COMPENSATING. The amount is measured, never asked for.
    measured = _day_surplus(db, setting, body.event_date)
    if measured.meal_count == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Nothing is logged on {body.event_date.isoformat()}, so there "
                f"is nothing to spread. A day with no meals on it is a day "
                f"nobody recorded, not a day of eating nothing."
            ),
        )
    if abs(measured.surplus_calories) < MIN_SURPLUS_KCAL:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{body.event_date.isoformat()} landed on its target. There is "
                f"nothing to make up."
            ),
        )

    parts = split_delta(-measured.surplus_calories, len(body.dates))
    return (
        [PlanEntry(d, part) for d, part in zip(body.dates, parts)],
        measured.surplus_calories,
    )


def _refuse_overlap(db: Session, user_id: int, entries: list[PlanEntry]) -> None:
    """409 if any day is already claimed, naming the plan that owns it.

    The unique index would raise anyway; catching it here is what turns an
    integrity error into a sentence. Refusing rather than merging is the same
    call Phase 10 made for renaming a food onto an occupied name: stacking two
    deltas on one day makes cancelling either of them ambiguous.
    """
    claimed = [entry.date for entry in entries]
    clash = db.scalars(
        select(CaloriePlanDay)
        .where(CaloriePlanDay.user_id == user_id, CaloriePlanDay.date.in_(claimed))
        .order_by(CaloriePlanDay.date)
    ).first()
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{clash.date.isoformat()} is already adjusted by the plan for "
                f"{clash.event_date.isoformat()}. Cancel that one first, or "
                f"choose different days."
            ),
        )


@router.delete("/{event_date}", status_code=204)
def cancel_plan(
    event_date: date_type,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cancel a plan, removing only the days it has not spent yet.

    Days already past keep their adjustment, and that asymmetry is the point.
    Those targets are what the user actually ate against; deleting them would
    retroactively re-measure finished days against a number that was never on
    screen at the time -- the same reason a plan may not be written onto a past
    date in the first place. Cancelling is undoing what is left, not erasing
    that the plan happened.

    Scoped on user_id, so another account's plan is a 404 rather than a
    deletion.
    """
    today = date_type.today()
    rows = db.scalars(
        select(CaloriePlanDay).where(
            CaloriePlanDay.user_id == user.id,
            CaloriePlanDay.event_date == event_date,
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No plan for that day")

    upcoming = [row for row in rows if row.date >= today]
    if not upcoming:
        raise HTTPException(
            status_code=409,
            detail=(
                "Every day in that plan has already happened, so there is "
                "nothing left to cancel."
            ),
        )

    for row in upcoming:
        db.delete(row)
    db.commit()
