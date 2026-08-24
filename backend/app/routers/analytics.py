from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Meal, User
from ..schemas import AnalyticsSummary, DayTotals

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/daily", response_model=AnalyticsSummary)
def daily_summary(
    start: date_type | None = None,
    end: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-day macro totals, plus totals and daily averages over the range."""
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")
    stmt = (
        select(
            Meal.date,
            func.sum(Meal.calories).label("calories"),
            func.sum(Meal.protein).label("protein"),
            func.sum(Meal.carbs).label("carbs"),
            func.sum(Meal.fat).label("fat"),
        )
        .where(Meal.user_id == user.id)
        .group_by(Meal.date)
        .order_by(Meal.date)
    )
    if start is not None:
        stmt = stmt.where(Meal.date >= start)
    if end is not None:
        stmt = stmt.where(Meal.date <= end)

    rows = db.execute(stmt).all()

    days = [
        DayTotals(
            date=row.date,
            calories=round(row.calories or 0, 2),
            protein=round(row.protein or 0, 2),
            carbs=None if row.carbs is None else round(row.carbs, 2),
            fat=None if row.fat is None else round(row.fat, 2),
        )
        for row in rows
    ]

    # Averages are per *logged* day, not per calendar day in the range.
    #
    # Dividing by calendar days treats a day with no meals as a day of zero
    # intake, and that is a claim about the user, not a neutral convention:
    # nobody eats nothing. In practice an unlogged day means "did not log",
    # so that denominator quietly reported people as eating hundreds of kcal
    # less than they did — the more days they missed, the further off it got,
    # and the number gave no hint it was happening.
    #
    # Each macro divides by the days *it* was recorded on. This reverses an
    # earlier decision here, and the reasoning is worth keeping: one shared
    # denominator was chosen so a macro logged on only some days could not look
    # inflated beside the others. It bought that at the cost of the number
    # being wrong. Someone who recorded carbs on 2 of 10 logged days was shown
    # a carbs "average" a fifth of what they actually ate on the days they
    # recorded it — a figure labelled "average" that was not the average of
    # anything. The comparability problem is real but it is a *presentation*
    # problem, and it is answered by `average_days` travelling with the numbers
    # so each average renders beside the sample it was built from.
    #
    # calories and protein are NOT NULL on meals, so their counts always equal
    # logged_days; only carbs and fat can differ.
    logged_days = len(days)

    totals: dict[str, float] = {}
    averages: dict[str, float] = {}
    average_days: dict[str, int] = {}
    for macro in ("calories", "protein", "carbs", "fat"):
        # `day.<macro>` is None only when no meal that day recorded it, so this
        # already drops exactly the days the macro is absent from — the
        # numerator was never the wrong half.
        values = [v for day in days if (v := getattr(day, macro)) is not None]
        totals[macro] = round(sum(values), 2)
        average_days[macro] = len(values)
        averages[macro] = round(sum(values) / len(values), 2) if values else 0.0

    return AnalyticsSummary(
        days=days,
        totals=totals,
        averages=averages,
        logged_days=logged_days,
        average_days=average_days,
    )
