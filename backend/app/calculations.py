from collections.abc import Sequence
from datetime import date as date_type
from datetime import timedelta
from typing import NamedTuple

# Smoothing factor for the weight trend line. 0.25 is a chosen convention, not a
# measured constant: it weights each new weigh-in at a quarter and gives roughly
# a one-week effective window, which is the usual way to see past day-to-day
# water and gut-content swings. Change it and the trend line changes shape; no
# number here is derived from anything.
WEIGHT_TREND_ALPHA = 0.25

# The rate of change is fitted over the last 4 weeks of trend, and refuses to
# answer below a week of weigh-ins. Both are policy choices about how much data
# is enough to show a number, not statistical thresholds.
RATE_WINDOW_DAYS = 28
RATE_MIN_POINTS = 7


class TrendPoint(NamedTuple):
    """One weigh-in with its smoothed value."""

    date: date_type
    weight_kg: float
    trend_kg: float


def weight_trend(
    entries: Sequence[tuple[date_type, float]],
    alpha: float = WEIGHT_TREND_ALPHA,
) -> list[TrendPoint]:
    """Exponentially weighted moving average over logged weigh-ins.

    The EWMA steps *per entry*, not per calendar day: a gap of a week and a gap
    of a day advance the smoothing equally. That is a deliberate simplification
    — at the daily-ish cadence people actually weigh themselves the difference
    is small, and it keeps the series defined without inventing weights for days
    nobody stood on the scale. Entries are sorted by date; the first entry seeds
    the trend at its own value, so early points track raw weight closely.
    """
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")

    points: list[TrendPoint] = []
    trend: float | None = None
    for entry_date, weight in sorted(entries, key=lambda item: item[0]):
        trend = weight if trend is None else alpha * weight + (1 - alpha) * trend
        points.append(TrendPoint(entry_date, weight, round(trend, 3)))
    return points


def weekly_rate(
    trend_points: Sequence[TrendPoint],
    window_days: int = RATE_WINDOW_DAYS,
    min_points: int = RATE_MIN_POINTS,
) -> float | None:
    """kg per week, as the least-squares slope of the recent *trend* series.

    Fitted against calendar-day offsets, so missed days do not compress the
    timeline. Returns None rather than a number when the window holds fewer
    than `min_points` weigh-ins — a rate built from two readings is noise
    wearing a decimal point.
    """
    if not trend_points:
        return None

    latest = max(point.date for point in trend_points)
    cutoff = latest - timedelta(days=window_days - 1)
    window = [point for point in trend_points if point.date >= cutoff]
    if len(window) < min_points:
        return None

    origin = min(point.date for point in window)
    xs = [(point.date - origin).days for point in window]
    ys = [point.trend_kg for point in window]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:  # every point on one day — no slope to fit
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    return round(slope * 7, 3)


def scale_macros(
    weight: float,
    serving_size: float,
    per_serving: dict[str, float | None],
) -> dict[str, float | None]:
    """Scale per-serving macro values to the weight actually eaten.

    Keys with None values (untracked macros) stay None.
    """
    if serving_size <= 0:
        raise ValueError("Serving size must be greater than zero")
    if weight < 0:
        raise ValueError("Weight cannot be negative")

    factor = weight / serving_size
    return {
        key: None if value is None else round(value * factor, 2)
        for key, value in per_serving.items()
    }


def total_macros(items: list[dict[str, float | None]]) -> dict[str, float | None]:
    """Sum macros across ingredients. A macro totals to None only if no
    ingredient reported it; otherwise missing values count as 0."""
    keys = ("calories", "protein", "carbs", "fat")
    totals: dict[str, float | None] = {}
    for key in keys:
        values = [item[key] for item in items if item.get(key) is not None]
        totals[key] = round(sum(values), 2) if values else None
    return totals
