import asyncio

import pytest

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
    def __init__(self, payload, status=200, url="https://example.test"):
        self._payload = payload
        self._status = status
        self._url = url

    def raise_for_status(self):
        if self._status >= 400:
            request = off_client.httpx.Request("GET", self._url)
            raise off_client.httpx.HTTPStatusError(
                "error", request=request,
                response=off_client.httpx.Response(self._status, request=request),
            )

    def json(self):
        if isinstance(self._payload, str):  # an HTML error page, not JSON
            raise ValueError("Expecting value")
        return self._payload


def _install_fake_http(monkeypatch, payload, fallback=None):
    """`payload` answers the classic endpoint and `fallback` the search service.
    Either may be a dict (JSON 200), a str (an HTML body), an int (that HTTP
    status, empty body) or an exception instance (raised by get). Returns the
    list of URLs requested, in order."""
    calls = []

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, params=None):
            calls.append(url)
            answer = fallback if url == off_client.FALLBACK_SEARCH_URL else payload
            if isinstance(answer, Exception):
                raise answer
            if isinstance(answer, int):
                return _FakeResponse("", status=answer, url=url)
            return _FakeResponse(answer, url=url)

    monkeypatch.setattr(off_client.httpx, "AsyncClient", FakeAsyncClient)
    return calls


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


# --- classic endpoint first, search service as the fallback -----------------

_FALLBACK_HITS = {"hits": [
    {
        "product_name": "Greek Style Yogurt Peach &amp; Passion Fruit",
        "brands": ["Milbona", "Lidl"],
        "nutriments": {"energy-kcal_100g": 133, "proteins_100g": 3.9},
    },
]}


def test_classic_success_never_asks_the_fallback(monkeypatch):
    calls = _install_fake_http(
        monkeypatch,
        {"products": [{"product_name": "Oats", "nutriments": {
            "energy-kcal_100g": 379, "proteins_100g": 13.2,
        }}]},
        fallback=AssertionError("the fallback must not be called"),
    )
    results = asyncio.run(off_client.search_products("oats"))
    assert [p.name for p in results] == ["Oats"]
    assert calls == [off_client.SEARCH_URL]


def test_classic_503_falls_back_to_search_service(monkeypatch):
    calls = _install_fake_http(monkeypatch, 503, fallback=_FALLBACK_HITS)
    results = asyncio.run(off_client.search_products("peach"))
    assert calls == [off_client.SEARCH_URL, off_client.FALLBACK_SEARCH_URL]
    [yogurt] = results
    assert yogurt.serving_size == 100  # the search service has no servings
    assert yogurt.calories == 133 and yogurt.protein == 3.9


def test_classic_timeout_falls_back(monkeypatch):
    calls = _install_fake_http(
        monkeypatch, off_client.httpx.ReadTimeout("slow"), fallback=_FALLBACK_HITS
    )
    assert len(asyncio.run(off_client.search_products("peach"))) == 1
    assert calls[-1] == off_client.FALLBACK_SEARCH_URL


def test_classic_html_body_falls_back(monkeypatch):
    # A 200 that is an HTML page is the same outage, whatever the status says.
    _install_fake_http(
        monkeypatch, "<html>Page temporarily unavailable</html>", fallback=_FALLBACK_HITS
    )
    assert len(asyncio.run(off_client.search_products("peach"))) == 1


def test_both_failing_raises_for_the_router(monkeypatch):
    calls = _install_fake_http(monkeypatch, 503, fallback=502)
    with pytest.raises(off_client.httpx.HTTPStatusError):
        asyncio.run(off_client.search_products("peach"))
    assert len(calls) == 2  # one try each, no retry loop


def test_list_brands_and_html_entities_are_normalized(monkeypatch):
    _install_fake_http(monkeypatch, 503, fallback=_FALLBACK_HITS)
    [yogurt] = asyncio.run(off_client.search_products("peach"))
    assert yogurt.name == "Greek Style Yogurt Peach & Passion Fruit"
    assert yogurt.brand == "Milbona"
