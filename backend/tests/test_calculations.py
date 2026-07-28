from datetime import date, timedelta

import pytest

from app.calculations import (
    TrendPoint,
    scale_macros,
    total_macros,
    weekly_rate,
    weight_trend,
)


def series(weights: list[float], start: date = date(2026, 6, 1), step: int = 1):
    """Weigh-ins `step` days apart, oldest first."""
    return [(start + timedelta(days=i * step), w) for i, w in enumerate(weights)]


def trend_series(trends: list[float], start: date = date(2026, 6, 1), step: int = 1):
    """Already-smoothed points, for testing the slope fit on its own.

    weekly_rate fits the *trend* series, and an EWMA lags a ramp before it
    settles — so feeding raw weights through weight_trend and expecting the raw
    slope back would be testing the lag, not the fit.
    """
    return [
        TrendPoint(start + timedelta(days=i * step), value, value)
        for i, value in enumerate(trends)
    ]


def test_weight_trend_seeds_on_the_first_entry():
    points = weight_trend(series([80.0]))
    assert len(points) == 1
    assert points[0].weight_kg == 80.0
    assert points[0].trend_kg == 80.0


def test_weight_trend_lags_behind_a_jump():
    points = weight_trend(series([80.0, 80.0, 84.0]))
    # alpha=0.25: the trend takes a quarter of the 4 kg spike, not all of it.
    assert points[-1].weight_kg == 84.0
    assert points[-1].trend_kg == pytest.approx(81.0)


def test_weight_trend_converges_on_a_stable_weight():
    points = weight_trend(series([90.0] + [80.0] * 40))
    assert points[-1].trend_kg == pytest.approx(80.0, abs=0.01)


def test_weight_trend_sorts_unordered_entries():
    unsorted = [(date(2026, 6, 3), 82.0), (date(2026, 6, 1), 80.0)]
    points = weight_trend(unsorted)
    assert [p.date for p in points] == [date(2026, 6, 1), date(2026, 6, 3)]
    assert points[0].trend_kg == 80.0


def test_weight_trend_steps_per_entry_not_per_calendar_day():
    """The documented simplification: a gap does not decay the trend faster."""
    daily = weight_trend(series([80.0, 84.0], step=1))
    weekly = weight_trend(series([80.0, 84.0], step=7))
    assert daily[-1].trend_kg == weekly[-1].trend_kg


def test_weekly_rate_is_negative_on_a_losing_trend():
    points = weight_trend(series([85.0 - 0.1 * i for i in range(14)]))
    rate = weekly_rate(points)
    assert rate is not None and rate < 0


def test_weekly_rate_is_positive_on_a_gaining_trend():
    points = weight_trend(series([70.0 + 0.1 * i for i in range(14)]))
    rate = weekly_rate(points)
    assert rate is not None and rate > 0


def test_weekly_rate_is_none_below_the_minimum_points():
    assert weekly_rate(weight_trend(series([80.0]))) is None
    assert weekly_rate(weight_trend(series([80.0] * 6))) is None
    assert weekly_rate(weight_trend(series([80.0] * 7))) is not None


def test_weekly_rate_is_none_without_any_points():
    assert weekly_rate([]) is None


def test_weekly_rate_ignores_entries_before_the_window():
    ancient = trend_series([120.0], start=date(2025, 1, 1))
    recent = trend_series([80.0] * 10, start=date(2026, 6, 1))
    # The 2025 outlier is outside the 28-day window, so it cannot bend the rate.
    assert weekly_rate(ancient + recent) == pytest.approx(0.0, abs=0.001)


def test_weekly_rate_fits_against_calendar_days_not_entry_index():
    """Weekly means seven calendar days, so gaps must not compress the fit."""
    # 0.2 kg per weigh-in, weighing in every second day: 0.1 kg/day = 0.7 kg/week.
    # Fitting against the entry index instead would double it to 1.4.
    every_other_day = trend_series([80.0 - 0.2 * i for i in range(8)], step=2)
    assert weekly_rate(every_other_day) == pytest.approx(-0.7, abs=0.001)


def test_weekly_rate_is_flat_on_an_unchanged_trend():
    assert weekly_rate(trend_series([80.0] * 10)) == 0.0


def test_weight_trend_rejects_an_out_of_range_alpha():
    with pytest.raises(ValueError):
        weight_trend(series([80.0]), alpha=0)
    with pytest.raises(ValueError):
        weight_trend(series([80.0]), alpha=1.5)


def test_scale_macros_scales_by_weight():
    result = scale_macros(200, 100, {"calories": 165, "protein": 31, "carbs": 0, "fat": 3.6})
    assert result == {"calories": 330, "protein": 62, "carbs": 0, "fat": 7.2}


def test_scale_macros_preserves_untracked_none():
    result = scale_macros(150, 100, {"calories": 100, "protein": 10, "carbs": None, "fat": None})
    assert result["calories"] == 150
    assert result["carbs"] is None
    assert result["fat"] is None


def test_scale_macros_rejects_zero_serving():
    with pytest.raises(ValueError):
        scale_macros(100, 0, {"calories": 100})


def test_scale_macros_rejects_negative_weight():
    with pytest.raises(ValueError):
        scale_macros(-5, 100, {"calories": 100})


def test_total_macros_sums_items():
    items = [
        {"calories": 100, "protein": 10, "carbs": 20, "fat": 5},
        {"calories": 50.5, "protein": 4.5, "carbs": None, "fat": 1},
    ]
    assert total_macros(items) == {"calories": 150.5, "protein": 14.5, "carbs": 20, "fat": 6}


def test_total_macros_all_missing_stays_none():
    items = [{"calories": 100, "protein": 10}, {"calories": 50, "protein": 5}]
    totals = total_macros(items)
    assert totals["carbs"] is None
    assert totals["fat"] is None
