"""Daily water logging.

Three verbs over event rows. `/api/steps` in a later phase is expected to
mirror this shape exactly, which is the point of keeping it plain.

**Nothing here may recompute calorie targets.** `routers/weights.py` and
`routers/settings.py` both call `apply_auto_targets`, so copying one of them
into a new daily-log router is the obvious mistake to make -- and it would be
wrong twice over. Water weight is precisely the day-to-day noise
`weight_trend` exists to smooth away, so it is not an input to any target; and
a measured TDEE deliberately stops at *yesterday* so that what you log today
cannot move the goal you are eating towards today. A write here that touched
targets would reopen that loop.
"""
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..calculations import water_goal
from ..db import get_db
from ..models import Setting, User
from ..models import WaterLog as WaterRow
from ..schemas import WaterDay, WaterEntry, WaterEntryCreate, WaterGoalBasis
from ..targets import _latest_trend_weight

router = APIRouter(prefix="/api/water", tags=["water"])


def _day(db: Session, user_id: int, day: date_type) -> WaterDay:
    """One day's entries, their total, and the goal to measure them against.

    The goal is resolved server-side and travels with the total. Deriving it in
    the client would be a second definition of a number this app already
    defines once -- the same rule that keeps `weight_trend` off the frontend.
    """
    rows = db.scalars(
        select(WaterRow)
        .where(WaterRow.user_id == user_id, WaterRow.date == day)
        # Newest first, so "undo" is entries[0] and the client never sorts.
        # `id` breaks ties: two taps inside the same second are common, and
        # created_at alone would leave their order undefined.
        .order_by(WaterRow.created_at.desc(), WaterRow.id.desc())
    ).all()

    setting = db.get(Setting, user_id)
    custom_ml = None if setting is None else setting.water_goal_ml
    # Only look up a weight when one is actually needed. A user with a custom
    # goal gets no query at all.
    weight_kg = None
    if custom_ml is None:
        weight = _latest_trend_weight(db, user_id)
        weight_kg = weight[0] if weight is not None else None

    goal = water_goal(weight_kg, custom_ml)

    return WaterDay(
        date=day,
        total_ml=float(sum(row.ml for row in rows)),
        goal_ml=goal.ml,
        goal_basis=WaterGoalBasis(
            source=goal.source, ml_per_kg=goal.ml_per_kg, weight_kg=goal.weight_kg
        ),
        entries=[WaterEntry.model_validate(row) for row in rows],
    )


@router.get("", response_model=WaterDay)
def get_water_day(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One day of water. Defaults to the server's today when no date is given.

    Always 200, never 404: a day with nothing logged is an ordinary state and
    the zero-total answer is the correct one, not an error.
    """
    return _day(db, user.id, date or date_type.today())


@router.post("", response_model=WaterEntry, status_code=201)
def add_water(
    entry: WaterEntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log one drink.

    An insert, not an upsert -- the opposite of POST /api/weights, and the
    difference is deliberate. A second weigh-in for a date corrects the first;
    a second glass of water is a second glass of water. 201 rather than
    weights' 200 for the same reason: a row is genuinely created every time,
    so the status can say so honestly.
    """
    row = WaterRow(user_id=user.id, date=entry.date, ml=entry.ml)
    db.add(row)
    db.commit()
    return row


@router.delete("/{entry_id}", status_code=204)
def delete_water(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove one entry. This is what the card's undo button calls.

    Scoped on user_id as well as id, so a guessed id from another account is a
    404 rather than a deletion -- the pattern every delete in this app follows.
    """
    row = db.scalars(
        select(WaterRow).where(WaterRow.id == entry_id, WaterRow.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Water entry not found")
    db.delete(row)
    db.commit()
