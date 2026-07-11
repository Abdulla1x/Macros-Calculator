import asyncio

from app.services import off_client
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
    assert product.carbs == 27
    assert product.fat == 2.5


def test_zero_gram_macros_survive_normalization():
    # A genuine 0 g value must stay 0, not become None (or vice versa).
    nutriments = {
        "energy-kcal_100g": 375, "proteins_100g": 12.5,
        "carbohydrates_100g": 0, "fat_100g": 0.0,
    }
    product = _per_serving(nutriments, serving_quantity=None)
    assert product.carbs == 0.0
    assert product.fat == 0.0


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


# --- search_products JSON handling (fake httpx client, no network) ----------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _install_fake_http(monkeypatch, payload):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url, params=None):
            return _FakeResponse(payload)

    monkeypatch.setattr(off_client.httpx, "AsyncClient", FakeAsyncClient)


def test_search_products_normalizes_real_shape(monkeypatch):
    _install_fake_http(monkeypatch, {"products": [
        {
            "product_name": "Greek Yogurt",
            "brands": "FitBrand, Parent Corp",
            "serving_quantity": "170",
            "nutriments": {
                "energy-kcal_serving": 100, "proteins_serving": 17,
                "carbohydrates_serving": 6, "fat_serving": 0.7,
            },
        },
        # No name → dropped.
        {"product_name": "  ", "nutriments": {"energy-kcal_100g": 50, "proteins_100g": 3}},
        # No usable macros → dropped.
        {"product_name": "Mystery Snack", "nutriments": {}},
        # Per-100g fallback, no brand.
        {"product_name": "Plain Oats", "nutriments": {
            "energy-kcal_100g": 379, "proteins_100g": 13.2,
        }},
    ]})

    results = asyncio.run(off_client.search_products("yogurt"))
    assert [p.name for p in results] == ["Greek Yogurt", "Plain Oats"]

    yogurt, oats = results
    assert yogurt.brand == "FitBrand"  # first brand only
    assert yogurt.serving_size == 170  # string serving_quantity coerced
    assert yogurt.calories == 100 and yogurt.protein == 17
    assert oats.brand is None
    assert oats.serving_size == 100 and oats.carbs is None


def test_search_products_handles_empty_payload(monkeypatch):
    _install_fake_http(monkeypatch, {})
    assert asyncio.run(off_client.search_products("nothing")) == []
