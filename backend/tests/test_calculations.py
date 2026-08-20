from datetime import date, timedelta

import pytest

from app.calculations import (
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
    KCAL_PER_KG,
    TDEE_PLAUSIBLE_BMR_RANGE,
    TrendPoint,
    activity_multiplier,
    age_years,
    bmi,
    bmr_mifflin_st_jeor,
    clamp_measured_tdee,
    estimated_tdee,
    macro_targets,
    measured_tdee,
    scale_macros,
    target_calories,
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


# --- Body profile → energy targets -------------------------------------------


def test_age_years_counts_the_birthday_itself_as_the_new_age():
    born = date(1990, 5, 4)
    assert age_years(born, on=date(2026, 5, 3)) == 35
    assert age_years(born, on=date(2026, 5, 4)) == 36
    assert age_years(born, on=date(2026, 5, 5)) == 36


def test_age_years_handles_a_december_birthday_in_january():
    assert age_years(date(1990, 12, 31), on=date(2026, 1, 1)) == 35


def test_bmi_is_none_when_either_input_is_missing():
    """Both inputs are optional profile fields, so "unknown" is not an error."""
    assert bmi(None, 180) is None
    assert bmi(80, None) is None
    assert bmi(80, 0) is None


def test_bmi_matches_the_definition():
    # 80 kg / 1.80 m² = 80 / 3.24 = 24.69…
    assert bmi(80, 180) == pytest.approx(24.7, abs=0.05)


def test_bmr_matches_a_hand_worked_mifflin_st_jeor():
    # 10(80) + 6.25(180) - 5(35) + 5 = 800 + 1125 - 175 + 5 = 1755
    assert bmr_mifflin_st_jeor(80, 180, 35, "male") == pytest.approx(1755, abs=0.05)
    # The female offset is -161 rather than +5, a 166 kcal difference.
    assert bmr_mifflin_st_jeor(80, 180, 35, "female") == pytest.approx(1589, abs=0.05)


def test_bmr_rejects_an_unknown_sex_rather_than_guessing():
    with pytest.raises(ValueError):
        bmr_mifflin_st_jeor(80, 180, 35, "unspecified")


def test_bmr_rejects_impossible_measurements():
    with pytest.raises(ValueError):
        bmr_mifflin_st_jeor(0, 180, 35, "male")
    with pytest.raises(ValueError):
        bmr_mifflin_st_jeor(80, 0, 35, "male")


def test_activity_multiplier_raises_rather_than_defaulting_to_sedentary():
    """A silent fallback would make a bad stored level read as a real TDEE."""
    with pytest.raises(ValueError):
        activity_multiplier("athlete")


def test_estimated_tdee_is_bmr_times_the_multiplier():
    # 1755 * 1.55 (moderate) = 2720.25
    assert estimated_tdee(80, 180, 35, "male", "moderate") == pytest.approx(
        2720.25, abs=0.1
    )


def test_target_calories_applies_the_requested_rate_when_it_is_reasonable():
    # -0.5 kg/week * 7700 kcal/kg / 7 days = -550 kcal/day, off a 3000 TDEE.
    result = target_calories(3000, -0.5, "male")
    assert result.calories == 2450
    assert result.clamped_reason is None


def test_target_calories_reports_both_clamps_when_both_fire():
    """Asking for -5 kg/week trips the rate cap, and the result trips the floor.

    The rate is capped at -1 kg/week, giving 3000 - 1100 = 1900; the floor is
    max(1500 absolute, 0.75 * 3000 = 2250), so 1900 is raised again. The user
    asked for a rate and got neither it nor the target it implies, and needs
    telling twice over.
    """
    result = target_calories(3000, -5, "male")
    assert result.calories == 2250
    assert "Rate limited" in result.clamped_reason
    assert "Raised to" in result.clamped_reason


def test_target_calories_never_returns_below_the_floor():
    """A legal rate can still land somewhere nobody should eat."""
    result = target_calories(2000, -1, "female")
    # 2000 - 1100 = 900, below both the 1200 absolute floor and the 1500
    # fractional one (0.75 * 2000). The higher of the two wins.
    assert result.calories == 1500
    assert "Raised to" in result.clamped_reason


def test_target_calories_leaves_a_surplus_alone():
    result = target_calories(2500, 0.25, "male")
    assert result.calories == pytest.approx(2775, abs=1)
    assert result.clamped_reason is None


def test_macro_targets_sum_back_to_the_calorie_target():
    macros = macro_targets(2400, 80)
    total = (
        macros["protein"] * KCAL_PER_G_PROTEIN
        + macros["carbs"] * KCAL_PER_G_CARB
        + macros["fat"] * KCAL_PER_G_FAT
    )
    # Within the rounding to whole grams, which can move each macro by half a
    # gram — up to about 9 kcal once fat is weighted.
    assert total == pytest.approx(2400, abs=10)


def test_macro_targets_scale_protein_with_body_weight_not_calories():
    """The reason this is not a fixed percentage split.

    Halving the calorie target must not halve protein: during a cut protein is
    the macro that matters most and calories the one that matters least.
    """
    heavy = macro_targets(2400, 100)
    light = macro_targets(2400, 60)
    assert heavy["protein"] > light["protein"]

    cutting = macro_targets(1600, 80)
    maintaining = macro_targets(2400, 80)
    assert cutting["protein"] == maintaining["protein"]


def test_macro_targets_floor_carbs_at_zero_rather_than_going_negative():
    # 200 kg of body weight against a 1200 kcal target: protein alone is 360 g
    # = 1440 kcal, already over budget before fat is counted.
    macros = macro_targets(1200, 200)
    assert macros["carbs"] == 0
    assert macros["protein"] > 0


# --- measured TDEE (energy balance) ------------------------------------------


def test_measured_tdee_equals_intake_when_weight_is_stable():
    """Holding weight means everything eaten was burned. The definition."""
    assert measured_tdee(2500, 0.0) == pytest.approx(2500)


def test_measured_tdee_subtracts_what_was_stored_as_tissue():
    # Gaining 0.7 kg/week banks 0.7 * 7700 / 7 = 770 kcal a day, so a 3000 kcal
    # intake means 2230 was actually burned.
    assert measured_tdee(3000, 0.7) == pytest.approx(2230, abs=0.1)


def test_measured_tdee_adds_back_what_was_drawn_from_tissue():
    """Losing weight means burning more than was eaten, not less."""
    assert measured_tdee(2000, -0.5) == pytest.approx(
        2000 + (0.5 / 7) * KCAL_PER_KG, abs=0.1
    )


def test_measured_tdee_matches_a_hand_worked_real_case():
    """The production hand-check this phase's thresholds were chosen against.

    Account with 22 logged days averaging 2712.3 kcal and a trend rise of
    0.159 kg/week: 2712.3 - (0.159/7)*7700 = 2537.4.
    """
    assert measured_tdee(2712.3, 0.159) == pytest.approx(2537.4, abs=1.0)


def test_clamp_leaves_a_believable_measurement_alone():
    result = clamp_measured_tdee(2538, bmr=1612)
    assert result.calories == 2538
    assert result.clamped_reason is None


def test_clamp_catches_a_tdee_below_resting_metabolism():
    """The under-logging failure, which is the dangerous one because it is silent.

    Someone logging far less than they eat produces a measured burn beneath
    their own BMR. That is impossible rather than surprising, so it is refused
    and explained rather than passed downstream into a starvation target.
    """
    low, _ = TDEE_PLAUSIBLE_BMR_RANGE
    result = clamp_measured_tdee(1100, bmr=1612)

    assert result.calories == round(1612 * low)
    assert result.clamped_reason is not None
    assert "aren't being logged" in result.clamped_reason


def test_clamp_catches_an_implausibly_high_tdee():
    _, high = TDEE_PLAUSIBLE_BMR_RANGE
    result = clamp_measured_tdee(9000, bmr=1612)

    assert result.calories == round(1612 * high)
    assert "mistyped weigh-in" in result.clamped_reason


def test_the_clamp_floor_is_not_reachable_by_under_logging():
    """Why the clamp anchors to BMR and not to the TDEE itself.

    `target_calories`'s existing floor is a fraction *of the TDEE*, so a TDEE
    dragged down by unlogged meals drags its own floor down with it and passes.
    BMR comes from body measurements, which intake cannot move -- so the same
    bad input that fools one check is caught by the other.
    """
    honest = clamp_measured_tdee(2538, bmr=1612)
    under_logged = clamp_measured_tdee(1200, bmr=1612)

    assert honest.clamped_reason is None
    assert under_logged.clamped_reason is not None
    # The floor did not move with the bad input.
    assert under_logged.calories > 1200
