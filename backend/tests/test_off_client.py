from app.services.off_client import _per_serving


def test_prefers_per_serving_values():
    nutriments = {
        "energy-kcal_serving": 150, "proteins_serving": 5,
        "carbohydrates_serving": 27, "fat_serving": 2.5,
        "energy-kcal_100g": 375, "proteins_100g": 12.5,
    }
    product = _per_serving(nutriments, serving_quantity=40)
    assert product.serving_size == 40
    assert product.calories == 150
    assert product.protein == 5


def test_falls_back_to_per_100g():
    nutriments = {"energy-kcal_100g": 375, "proteins_100g": 12.5, "fat_100g": 6.2}
    product = _per_serving(nutriments, serving_quantity=None)
    assert product.serving_size == 100
    assert product.calories == 375
    assert product.carbs is None
    assert product.fat == 6.2


def test_returns_none_without_usable_macros():
    assert _per_serving({}, serving_quantity=None) is None
    assert _per_serving({"energy-kcal_100g": "not-a-number"}, None) is None
