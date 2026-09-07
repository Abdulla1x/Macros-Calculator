from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..calculations import goal_projection, weekly_rate, weight_trend
from ..db import get_db
from ..models import Setting, User
from ..models import WeightEntry as WeightRow
from ..schemas import (
    GoalProjection,
    WeightEntry,
    WeightEntryCreate,
    WeightTrend,
    WeightTrendPoint,
)
from ..targets import apply_auto_targets
from ..upsert import upsert

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

    The smoothing, the rate and the goal projection all come from
    `calculations.py`; nothing is computed client-side, so there is one
    definition of the trend line.

    ⚠️ `days` decides what the numbers are built from, not merely what is
    drawn: `weight_trend`'s EWMA seeds at the first entry in the window and
    `weekly_rate` needs seven points inside 28 days. A client that narrows this
    to zoom a chart would move `latest_trend_kg`, `weekly_rate_kg` and the
    projected date with it, and a short enough window would blank the last two
    outright. The frontend therefore fetches once at the cap and slices for
    display -- see TREND_FETCH_DAYS in pages/Weight.tsx.
    """
    cutoff = date_type.today() - timedelta(days=days - 1)
    rows = db.scalars(
        select(WeightRow)
        .where(WeightRow.user_id == user.id, WeightRow.date >= cutoff)
        .order_by(WeightRow.date)
    ).all()

    points = weight_trend([(row.date, row.weight_kg) for row in rows])
    rate = weekly_rate(points)

    # db.get rather than the settings router's _get_or_create: a GET must not
    # write a row. An account old enough to predate settings-on-signup simply
    # has no goal weight, which is an answer the projection already has a
    # status for.
    setting = db.get(Setting, user.id)
    projected = goal_projection(
        None if setting is None else setting.goal_weight_kg,
        points,
        rate,
        date_type.today(),
    )

    return WeightTrend(
        points=[WeightTrendPoint.model_validate(point) for point in points],
        latest_trend_kg=points[-1].trend_kg if points else None,
        weekly_rate_kg=rate,
        point_count=len(points),
        # Field by field, deliberately -- not model_validate(projected), which
        # is what the line above does for WeightTrendPoint. The two are safe
        # for opposite reasons: WeightTrendPoint has no defaulted field, so a
        # name that stopped matching would raise, while every field here
        # defaults to None and a rename would serialise as null instead of
        # failing. That is the silent-default trap `_user_out`,
        # `_template_out` and `_settings_out` each exist to close.
        projection=GoalProjection(
            status=projected.status,
            goal_weight_kg=projected.goal_weight_kg,
            remaining_kg=projected.remaining_kg,
            weeks=projected.weeks,
            reach_date=projected.reach_date,
            from_date=projected.from_date,
        ),
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
    def build() -> WeightRow:
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
        # targets_auto on gets its goals recomputed here rather than only when
        # it next opens Settings. Without this the target would lag the weight
        # by however long it took the user to visit that page -- which is
        # precisely the "static number you guessed once" problem the profile
        # exists to fix.
        #
        # Flushed first so the new row is visible to the query inside
        # compute_targets; both writes then land on one commit. Inside build()
        # so a retry recomputes them too: a rollback discards this write along
        # with the weigh-in, and a target left at the pre-weigh-in value would
        # be the silent half of the bug.
        setting = db.get(Setting, user.id)
        if setting is not None:
            db.flush()
            apply_auto_targets(setting, db)
        return row

    return upsert(db, build)


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
