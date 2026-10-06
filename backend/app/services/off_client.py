"""Thin client for the Open Food Facts search API (no key required)."""
import html
import logging

import httpx

from ..schemas import OFFProduct

logger = logging.getLogger(__name__)

SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
# OFF's newer search service. It is the fallback, not the default, because its
# index holds per-100 g nutriments only -- no serving_quantity, no `_serving`
# values (checked 2026-10-06, 0 of 48 hits) -- so every row it returns is per
# 100 g. The classic endpoint has real servings but sheds load with a fast 503
# about half the time; asking it first keeps the servings whenever it answers.
FALLBACK_SEARCH_URL = "https://search.openfoodfacts.org/search"
# OFF asks API users to identify themselves via User-Agent.
USER_AGENT = "Trackaholic/2.0 (https://github.com/Abdulla1x/Trackaholic)"
FIELDS = "product_name,brands,serving_quantity,nutriments"
FALLBACK_FIELDS = "product_name,brands,nutriments"
# A healthy classic answer takes about a second. A shorter budget for it means a
# hang costs a few seconds before the fallback, not the whole wait.
CLASSIC_TIMEOUT_S = 6.0
FALLBACK_TIMEOUT_S = 10.0


def _per_serving(nutriments: dict, serving_quantity: float | None) -> OFFProduct | None:
    """Normalize a raw OFF product to macros per serving.

    Prefer real per-serving values; otherwise fall back to per-100g with a
    100 g serving so the numbers stay meaningful.
    """
    def num(key: str) -> float | None:
        value = nutriments.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if serving_quantity and num("energy-kcal_serving") is not None:
        suffix, serving_size = "_serving", float(serving_quantity)
    elif num("energy-kcal_100g") is not None:
        suffix, serving_size = "_100g", 100.0
    else:
        return None

    calories = num(f"energy-kcal{suffix}")
    protein = num(f"proteins{suffix}")
    if calories is None or protein is None:
        return None

    carbs = num(f"carbohydrates{suffix}")
    fat = num(f"fat{suffix}")
    return OFFProduct(
        name="",  # filled by caller
        serving_size=round(serving_size, 2),
        calories=round(calories, 2),
        protein=round(protein, 2),
        carbs=None if carbs is None else round(carbs, 2),
        fat=None if fat is None else round(fat, 2),
    )


def _first_brand(brands) -> str | None:
    """The first brand, from either shape: the classic endpoint sends a comma
    string ("FitBrand, Parent Corp"), the search service a list."""
    if isinstance(brands, str):
        brands = brands.split(",")
    if not isinstance(brands, list):
        return None
    for brand in brands:
        if isinstance(brand, str) and brand.strip():
            return brand.strip()
    return None


def _normalize(product: dict) -> OFFProduct | None:
    # OFF stores some names with their HTML entities still in ("Peach &amp;
    # Passion Fruit"), so they are decoded here, once, for both endpoints.
    name = html.unescape(product.get("product_name") or "").strip()
    if not name:
        return None
    try:
        serving_quantity = float(product.get("serving_quantity"))
    except (TypeError, ValueError):
        serving_quantity = None

    normalized = _per_serving(product.get("nutriments") or {}, serving_quantity)
    if normalized is None:
        return None
    normalized.name = name
    normalized.brand = _first_brand(product.get("brands"))
    return normalized


async def _fetch(url: str, params: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        # The classic endpoint's 503 is an HTML page; a 200 that is not JSON
        # is the same failure and must reach the fallback, not the caller.
        return response.json()


async def search_products(query: str, limit: int = 8) -> list[OFFProduct]:
    """At most two requests: the classic endpoint once, then the search service
    if it fails in any way. No retry loop -- OFF allows about 10 searches a
    minute per IP, and that IP is the server's, shared by every user. If both
    fail, the error propagates and the router answers 502."""
    classic_params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit,
        "fields": FIELDS,
    }
    try:
        payload = await _fetch(SEARCH_URL, classic_params, CLASSIC_TIMEOUT_S)
        products = payload.get("products", [])
        logger.info("OFF lookup: served by classic search")
    except Exception as error:
        # No query text in the log: the line is for counting, not for reading
        # what people search for.
        logger.info(
            "OFF lookup: classic failed (%s), trying search fallback",
            _describe(error),
        )
        fallback_params = {"q": query, "page_size": limit, "fields": FALLBACK_FIELDS}
        payload = await _fetch(FALLBACK_SEARCH_URL, fallback_params, FALLBACK_TIMEOUT_S)
        products = payload.get("hits", [])
        logger.info("OFF lookup: served by search fallback")

    return [p for p in (_normalize(product) for product in products) if p is not None]


def _describe(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return str(error.response.status_code)
    return type(error).__name__
