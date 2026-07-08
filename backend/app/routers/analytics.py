from datetime import date as date_type

from fastapi import APIRouter, Depends
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

    totals: dict[str, float] = {}
    averages: dict[str, float] = {}
    for macro in ("calories", "protein", "carbs", "fat"):
        values = [v for day in days if (v := getattr(day, macro)) is not None]
        totals[macro] = round(sum(values), 2)
        averages[macro] = round(sum(values) / len(values), 2) if values else 0.0

    return AnalyticsSummary(days=days, totals=totals, averages=averages)
