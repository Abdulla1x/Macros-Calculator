import pytest

from app.calculations import scale_macros, total_macros


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
