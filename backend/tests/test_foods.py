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


def test_search_treats_percent_and_underscore_as_literal_characters(client):
    """LIKE wildcards typed into the search box used to match anything.

    "100%" is a real thing to type -- half the bread in a supermarket is named
    that way -- and before the escape it matched every food in the library,
    because the trailing % is the wildcard. The failure is silent: ten plausible
    rows come back, just not the ones asked for.
    """
    for name in ("100% Whole Wheat", "100g Oats", "Plain Rice"):
        client.post("/api/foods", json=_chicken(name=name))

    results = client.get("/api/foods/search", params={"q": "100%"}).json()
    assert [food["name"] for food in results] == ["100% Whole Wheat"]

    # `_` is the subtler one: it matches any single character, so a one-key
    # search used to return the whole library.
    assert client.get("/api/foods/search", params={"q": "_"}).json() == []


def test_search_finds_a_name_containing_a_backslash(client):
    """The escape character itself has to survive being searched for.

    _escape_like doubles backslashes before it adds any, so a name with one in
    it stays findable rather than turning the next character into an escape.
    """
    client.post("/api/foods", json=_chicken(name="Back\\slash Bar"))

    results = client.get("/api/foods/search", params={"q": "Back\\"}).json()
    assert [food["name"] for food in results] == ["Back\\slash Bar"]


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


def test_put_renames_in_place_instead_of_creating_a_second_row(client):
    """The hole PUT exists to close.

    POST upserts on the *name*, so a changed name matches nothing and inserts.
    Before this endpoint there was no way to correct a name -- only to end up
    with the typo and the fix sitting in the library side by side.
    """
    food_id = client.post("/api/foods", json=_chicken(name="Chikcen Breast")).json()["id"]

    response = client.put(f"/api/foods/{food_id}", json=_chicken(name="Chicken Breast"))
    assert response.status_code == 200

    foods = client.get("/api/foods").json()
    assert [food["name"] for food in foods] == ["Chicken Breast"]
    assert foods[0]["id"] == food_id


def test_put_onto_an_existing_name_is_refused_and_changes_nothing(client):
    """409 rather than merging the two rows.

    Folding them together would delete a row the user never asked to lose, so
    the conflict goes back to them to resolve. Both rows must survive intact --
    a refusal that half-applied would be worse than either outcome.
    """
    keeper = client.post("/api/foods", json=_chicken()).json()
    other = client.post(
        "/api/foods", json=_chicken(name="Chickpeas", calories=164)
    ).json()

    # Case-insensitively the same name, because the index is on lower(name).
    response = client.put(
        f"/api/foods/{other['id']}", json=_chicken(name="chicken BREAST")
    )
    assert response.status_code == 409

    foods = {food["name"]: food for food in client.get("/api/foods").json()}
    assert set(foods) == {"Chicken Breast", "Chickpeas"}
    assert foods["Chicken Breast"]["id"] == keeper["id"]
    assert foods["Chickpeas"]["calories"] == 164


def test_put_unknown_id_is_404(client):
    assert client.put("/api/foods/9999", json=_chicken()).status_code == 404


def test_correcting_a_number_makes_an_off_row_yours(client):
    """An edited Open Food Facts row is no longer what Open Food Facts said.

    The badge is the app telling the user which figures to trust. Leaving it on
    numbers they typed themselves would be the one lie this section cannot
    afford.
    """
    food = client.post(
        "/api/foods", json=_chicken(source="openfoodfacts")
    ).json()
    assert food["source"] == "openfoodfacts"

    updated = client.put(
        f"/api/foods/{food['id']}", json=_chicken(source="openfoodfacts", calories=170)
    ).json()
    assert updated["source"] == "user"
    assert updated["calories"] == 170


def test_renaming_an_off_row_keeps_its_badge(client):
    """The other half of the rule, and the reason it is not "any save".

    A rename changes no number, so Open Food Facts still supplied every figure
    on the row. Flipping the badge here would throw away true provenance.
    """
    food = client.post("/api/foods", json=_chicken(source="openfoodfacts")).json()

    updated = client.put(
        f"/api/foods/{food['id']}",
        json=_chicken(source="openfoodfacts", name="Chicken breast, raw"),
    ).json()
    assert updated["source"] == "openfoodfacts"
    assert updated["name"] == "Chicken breast, raw"


def test_the_body_cannot_set_source_in_either_direction(client):
    """Provenance is the server's call, not the client's.

    FoodCreate carries a `source` because POST needs it -- that is the caller
    saying where a *new* row came from. On an existing row it is a claim about
    history the server already knows, so PUT ignores it and derives the answer
    from whether the numbers moved.
    """
    mine = client.post("/api/foods", json=_chicken(source="user")).json()
    theirs = client.post(
        "/api/foods", json=_chicken(name="Oat Flakes", source="openfoodfacts")
    ).json()

    # Nothing changed but the claimed source: both rows keep what they had.
    kept = client.put(
        f"/api/foods/{mine['id']}", json=_chicken(source="openfoodfacts")
    ).json()
    assert kept["source"] == "user"

    still_off = client.put(
        f"/api/foods/{theirs['id']}", json=_chicken(name="Oat Flakes", source="user")
    ).json()
    assert still_off["source"] == "openfoodfacts"


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
