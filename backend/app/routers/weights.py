from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..calculations import weekly_rate, weight_trend
from ..db import get_db
from ..models import Setting, User
from ..models import WeightEntry as WeightRow
from ..schemas import WeightEntry, WeightEntryCreate, WeightTrend, WeightTrendPoint
from ..targets import apply_auto_targets

router = APIRouter(prefix="/api/weights", tags=["weights"])


@router.get("", response_model=list[WeightEntry])
def list_weights(
    start: date_type | None = None,
    end: date_type | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")

    stmt = select(WeightRow).where(WeightRow.user_id == user.id)
    if start is not None:
        stmt = stmt.where(WeightRow.date >= start)
    if end is not None:
        stmt = stmt.where(WeightRow.date <= end)
    # Cap an unbounded query at the most recent `limit` days, then hand the
    # result back oldest-first so it reads as a series.
    rows = db.scalars(stmt.order_by(WeightRow.date.desc()).limit(limit)).all()
    return sorted(rows, key=lambda row: row.date)


@router.get("/trend", response_model=WeightTrend)
def get_trend(
    days: int = Query(default=90, ge=1, le=1825),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Weigh-ins over the last `days`, each with its smoothed trend value.

    The smoothing and the rate come from `calculations.py`; nothing is computed
    client-side, so there is one definition of the trend line.
    """
    cutoff = date_type.today() - timedelta(days=days - 1)
    rows = db.scalars(
        select(WeightRow)
        .where(WeightRow.user_id == user.id, WeightRow.date >= cutoff)
        .order_by(WeightRow.date)
    ).all()

    points = weight_trend([(row.date, row.weight_kg) for row in rows])
    return WeightTrend(
        points=[WeightTrendPoint.model_validate(point) for point in points],
        latest_trend_kg=points[-1].trend_kg if points else None,
        weekly_rate_kg=weekly_rate(points),
        point_count=len(points),
    )


@router.post("", response_model=WeightEntry)
def save_weight(
    entry: WeightEntryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a weigh-in, replacing any existing one for that date.

    Deliberately always 200, never 201: this is an upsert, and a status that
    flips between "created" and "updated" for an identical call tells the
    client something it cannot act on. The row is returned either way.

    SELECT-then-write rather than ON CONFLICT, because the dialect-specific
    upsert syntax differs between SQLite (dev/tests) and Postgres (production)
    and this runs on both.
    """
    row = db.scalars(
        select(WeightRow).where(
            WeightRow.user_id == user.id, WeightRow.date == entry.date
        )
    ).first()
    if row is None:
        row = WeightRow(
            user_id=user.id, date=entry.date, weight_kg=entry.weight_kg
        )
        db.add(row)
    else:
        row.weight_kg = entry.weight_kg

    # A weigh-in is an input to the calorie target, so an account with
    # targets_auto on gets its goals recomputed here rather than only when it
    # next opens Settings. Without this the target would lag the weight by
    # however long it took the user to visit that page -- which is precisely
    # the "static number you guessed once" problem the profile exists to fix.
    #
    # Flushed first so the new row is visible to the query inside
    # compute_targets; both writes then land on one commit.
    setting = db.get(Setting, user.id)
    if setting is not None:
        db.flush()
        apply_auto_targets(setting, db)

    db.commit()
    return row


@router.delete("/{weight_id}", status_code=204)
def delete_weight(
    weight_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalars(
        select(WeightRow).where(
            WeightRow.id == weight_id, WeightRow.user_id == user.id
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Weight entry not found")
    db.delete(row)
    db.commit()
