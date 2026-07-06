from datetime import date as date_type

from fastapi import APIRouter

from ..db import get_connection
from ..schemas import AnalyticsSummary, DayTotals

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/daily", response_model=AnalyticsSummary)
def daily_summary(start: date_type | None = None, end: date_type | None = None):
    """Per-day macro totals, plus totals and daily averages over the range."""
    query = """
        SELECT date,
               SUM(calories) AS calories,
               SUM(protein) AS protein,
               SUM(carbs) AS carbs,
               SUM(fat) AS fat
        FROM meals
    """
    conditions, params = [], []
    if start is not None:
        conditions.append("date >= ?")
        params.append(start.isoformat())
    if end is not None:
        conditions.append("date <= ?")
        params.append(end.isoformat())
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY date ORDER BY date"

    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    days = [
        DayTotals(
            date=row["date"],
            calories=round(row["calories"] or 0, 2),
            protein=round(row["protein"] or 0, 2),
            carbs=None if row["carbs"] is None else round(row["carbs"], 2),
            fat=None if row["fat"] is None else round(row["fat"], 2),
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
