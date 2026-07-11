"""Thin client for the Open Food Facts search API (no key required)."""
import httpx

from ..schemas import OFFProduct

SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
# OFF asks API users to identify themselves via User-Agent.
USER_AGENT = "MacrosCalculator/2.0 (https://github.com/Abdulla1x/Macros-Calculator)"
FIELDS = "product_name,brands,serving_quantity,nutriments"


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


async def search_products(query: str, limit: int = 8) -> list[OFFProduct]:
    params = {
        "search_terms": query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": limit,
        "fields": FIELDS,
    }
    async with httpx.AsyncClient(
        timeout=10.0, headers={"User-Agent": USER_AGENT}
    ) as client:
        response = await client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    results: list[OFFProduct] = []
    for product in payload.get("products", []):
        name = (product.get("product_name") or "").strip()
        if not name:
            continue
        try:
            serving_quantity = float(product.get("serving_quantity"))
        except (TypeError, ValueError):
            serving_quantity = None

        normalized = _per_serving(product.get("nutriments") or {}, serving_quantity)
        if normalized is None:
            continue
        normalized.name = name
        brands = (product.get("brands") or "").strip()
        normalized.brand = brands.split(",")[0].strip() or None if brands else None
        results.append(normalized)
    return results
