"""Daily step logging.

Three verbs over one row per day. The shape is water's, deliberately -- that
router says `/api/steps` is expected to mirror it -- with one difference that
comes from the data rather than from taste: a step count is a *day*, so POST
upserts the way `routers/weights.py` does instead of inserting the way
`routers/water.py` does.

**Nothing here may recompute calorie targets.** `routers/weights.py` and
`routers/settings.py` both call `apply_auto_targets`, and this router copies
weights' upsert body, which makes bringing that call along with it the easy
mistake. It would be wrong twice over. A measured TDEE already contains the
energy spent on every step taken inside its measurement window, so adding a
step-derived burn on top double-counts; and that window deliberately stops at
*yesterday* so what you log today cannot move the goal you are eating towards
today. Steps are recorded and shown. They are an input to nothing.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..calculations import steps_burn
from ..db import get_db
from ..models import Setting, User
from ..models import StepEntry as StepRow
from ..schemas import StepDay, StepEntry, StepEntryCreate
from ..targets import _latest_trend_weight

router = APIRouter(prefix="/api/steps", tags=["steps"])


def _row(db: Session, user_id: int, day: date_type) -> StepRow | None:
    """The one row for a user's day, if it exists.

    Shared by all three verbs because the unique index guarantees there is at
    most one -- the same query written once rather than three times slightly
    differently.
    """
    return db.scalars(
        select(StepRow).where(StepRow.user_id == user_id, StepRow.date == day)
    ).first()


def _day(db: Session, user_id: int, day: date_type) -> StepDay:
    """One day's count, the goal to measure it against, and what it burned.

    Both derived numbers are resolved server-side and travel with the count,
    the same rule the water card follows: deriving them in the client would be
    a second definition of numbers this app already defines once.
    """
    row = _row(db, user_id, day)
    steps = row.steps if row is not None else 0

    setting = db.get(Setting, user_id)
    goal = None if setting is None else setting.steps_goal

    # Only look up a weight when there is something to convert. A day with
    # nothing logged costs no extra query.
    weight_kg = None
    if steps > 0:
        weight = _latest_trend_weight(db, user_id)
        weight_kg = weight[0] if weight is not None else None

    return StepDay(
        date=day,
        steps=steps,
        # Not `steps > 0`: zero is a legal count, so a logged zero has to stay
        # distinguishable from a day nobody has touched.
        logged=row is not None,
        goal=goal,
        burn_kcal=steps_burn(steps, weight_kg),
        burn_weight_kg=weight_kg if steps > 0 else None,
    )


@router.get("", response_model=StepDay)
def get_step_day(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One day of steps. Defaults to the server's today when no date is given.

    Always 200, never 404: a day with nothing logged is an ordinary state, and
    a zero count with `logged` false is the correct answer rather than an error.
    """
    return _day(db, user.id, date or date_type.today())


@router.post("", response_model=StepEntry)
def save_steps(
    entry: StepEntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a day's step count, replacing any existing one for that date.

    An upsert, not an insert -- the opposite of POST /api/water, and the
    difference is the whole reason these two trackers do not share a table. A
    second glass of water is a second glass of water; a second reading of the
    pedometer is the same day's walking, counted later.

    Deliberately always 200, never 201, following POST /api/weights: a status
    that flips between "created" and "updated" for an identical call tells the
    client something it cannot act on.

    SELECT-then-write rather than ON CONFLICT, because the dialect-specific
    upsert syntax differs between SQLite (dev/tests) and Postgres (production)
    and this runs on both.
    """
    row = _row(db, user.id, entry.date)
    if row is None:
        row = StepRow(user_id=user.id, date=entry.date, steps=entry.steps)
        db.add(row)
    else:
        row.steps = entry.steps

    db.commit()
    return row


@router.delete("", status_code=204)
def clear_steps(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a day's count entirely, back to never having been logged.

    Not the same as saving a zero, which is why both exist: a zero says "I did
    not walk", where this says "I should not have logged this day at all" --
    the correction for a count typed against the wrong date.

    Scoped on user_id as well as date, so another account's day is a 404 rather
    than a deletion -- the pattern every delete in this app follows.
    """
    row = _row(db, user.id, date or date_type.today())
    if row is None:
        raise HTTPException(status_code=404, detail="No steps logged for that day")
    db.delete(row)
    db.commit()
