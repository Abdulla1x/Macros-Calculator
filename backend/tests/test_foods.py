from app.schemas import OFFProduct
from app.services import off_client
from conftest import post_raw_json


def _chicken(**overrides):
    food = {
        "name": "Chicken Breast",
        "serving_size": 100,
        "calories": 165,
        "protein": 31,
        "carbs": 0,
        "fat": 3.6,
        "source": "user",
    }
    food.update(overrides)
    return food


def test_save_and_search_case_insensitive(client):
    client.post("/api/foods", json=_chicken())
    client.post("/api/foods", json=_chicken(name="Chickpeas", calories=164, protein=8.9))

    results = client.get("/api/foods/search", params={"q": "chick"}).json()
    assert {food["name"] for food in results} == {"Chicken Breast", "Chickpeas"}

    results = client.get("/api/foods/search", params={"q": "BREAST"}).json()
    assert len(results) == 1


def test_saving_same_name_updates_macros(client):
    client.post("/api/foods", json=_chicken())
    client.post("/api/foods", json=_chicken(name="chicken breast", calories=170))

    foods = client.get("/api/foods").json()
    assert len(foods) == 1
    assert foods[0]["calories"] == 170


def test_rejects_non_finite_macros(client):
    """Same hole as MealCreate had: `inf >= 0` and `inf > 0` are both True.

    A food is the wider blast radius of the two — FoodAutocomplete writes one on
    every Open Food Facts pick, so a bad row would be read back into the meal
    form as well as into the export.
    """
    for field in ("serving_size", "calories", "protein", "carbs", "fat"):
        response = post_raw_json(
            client, "/api/foods", _chicken(**{field: float("inf")})
        )
        assert response.status_code == 422, f"{field}=inf was accepted"


def test_delete_food(client):
    food_id = client.post("/api/foods", json=_chicken()).json()["id"]
    assert client.delete(f"/api/foods/{food_id}").status_code == 204
    assert client.delete(f"/api/foods/{food_id}").status_code == 404


def test_lookup_returns_normalized_products(client, monkeypatch):
    async def fake_search(query, limit=8):
        return [OFFProduct(name="Oat Flakes", brand="Quaker", serving_size=40,
                           calories=150, protein=5, carbs=27, fat=2.5)]

    monkeypatch.setattr(off_client, "search_products", fake_search)
    results = client.get("/api/foods/lookup", params={"q": "oats"}).json()
    assert results[0]["name"] == "Oat Flakes"
    assert results[0]["source"] == "openfoodfacts"


def test_lookup_failure_returns_502(client, monkeypatch):
    async def broken_search(query, limit=8):
        raise RuntimeError("network down")

    monkeypatch.setattr(off_client, "search_products", broken_search)
    assert client.get("/api/foods/lookup", params={"q": "oats"}).status_code == 502
