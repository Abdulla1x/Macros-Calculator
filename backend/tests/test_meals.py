from conftest import post_raw_json


def _sample(**overrides):
    meal = {
        "date": "2026-07-01",
        "name": "Chicken & Rice",
        "calories": 560,
        "protein": 45,
        "carbs": 56,
        "fat": 8.5,
    }
    meal.update(overrides)
    return meal


def test_create_and_list_by_date(client):
    created = client.post("/api/meals", json=_sample()).json()
    assert created["id"] > 0

    client.post("/api/meals", json=_sample(date="2026-07-02", name="Other Day"))

    meals = client.get("/api/meals", params={"date": "2026-07-01"}).json()
    assert len(meals) == 1
    assert meals[0]["name"] == "Chicken & Rice"
    assert meals[0]["carbs"] == 56


def test_optional_macros_can_be_omitted(client):
    response = client.post(
        "/api/meals",
        json={"date": "2026-07-01", "name": "Simple", "calories": 300, "protein": 20},
    )
    assert response.status_code == 201
    assert response.json()["carbs"] is None


def test_rejects_negative_and_blank(client):
    assert client.post("/api/meals", json=_sample(calories=-5)).status_code == 422
    assert client.post("/api/meals", json=_sample(name="")).status_code == 422


def test_rejects_non_finite_macros(client):
    """Positive infinity is the one `ge=0` let through: `inf >= 0` is True.

    (`nan` and `-inf` were already refused by the bound itself.) Stored, one such
    value breaks the account two ways at once — GET /api/data/export/all 500s,
    because it returns a plain dict whose raw float meets Starlette's
    allow_nan=False, while GET /api/meals quietly reports `null` for a field
    types.ts declares as `number`.
    """
    for field in ("calories", "protein", "carbs", "fat"):
        for bad in (float("inf"), float("-inf"), float("nan")):
            response = post_raw_json(client, "/api/meals", _sample(**{field: bad}))
            assert response.status_code == 422, f"{field}={bad} was accepted"


def test_the_rejection_itself_renders(client):
    """Regression for the 422-that-500s, now reachable outside templates.

    FastAPI echoes the rejected value back under `input`, and Starlette
    serializes the body with allow_nan=False — so rendering this particular
    rejection used to crash. main.py's validation_error_handler is what fixes
    it; this is the first meals-side test that depends on it.
    """
    response = post_raw_json(client, "/api/meals", _sample(calories=float("inf")))
    assert response.status_code == 422
    assert "detail" in response.json()


def test_update_meal(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]

    response = client.put(
        f"/api/meals/{meal_id}",
        json=_sample(date="2026-07-03", name="  Chicken & Quinoa ", calories=610, fat=None),
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == meal_id
    assert updated["date"] == "2026-07-03"
    assert updated["name"] == "Chicken & Quinoa"
    assert updated["calories"] == 610
    assert updated["fat"] is None

    # The update moved the meal, not copied it.
    assert client.get("/api/meals", params={"date": "2026-07-01"}).json() == []
    assert [m["id"] for m in client.get("/api/meals").json()] == [meal_id]


def test_updated_at_is_null_until_the_meal_is_edited(client):
    created = client.post("/api/meals", json=_sample()).json()
    # A meal nobody has corrected has no edit time. Defaulting this to the
    # creation time would report every meal in the table as revised.
    assert created["updated_at"] is None

    edited = client.put(f"/api/meals/{created['id']}", json=_sample(calories=610)).json()
    assert edited["updated_at"] is not None

    # And it survives the round trip -- the stamp is stored, not just returned.
    listed = client.get("/api/meals", params={"date": "2026-07-01"}).json()
    assert listed[0]["updated_at"] == edited["updated_at"]


def test_editing_does_not_rewrite_when_the_meal_was_logged(client):
    created = client.post("/api/meals", json=_sample()).json()
    exported_before = client.get("/api/data/export/all").json()["meals"][0]

    client.put(f"/api/meals/{created['id']}", json=_sample(calories=610))
    exported_after = client.get("/api/data/export/all").json()["meals"][0]

    # A correction changes when the row last changed, never when the food was
    # first logged -- created_at is the usage signal and must not drift.
    assert exported_after["created_at"] == exported_before["created_at"]
    assert exported_before["updated_at"] is None
    assert exported_after["updated_at"] is not None


def test_update_meal_validates_and_404s(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]
    assert client.put(f"/api/meals/{meal_id}", json=_sample(calories=-5)).status_code == 422
    assert client.put(f"/api/meals/{meal_id}", json=_sample(name="")).status_code == 422
    assert client.put("/api/meals/99999", json=_sample()).status_code == 404


def test_delete_meal(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]
    assert client.delete(f"/api/meals/{meal_id}").status_code == 204
    assert client.delete(f"/api/meals/{meal_id}").status_code == 404
    assert client.get("/api/meals", params={"date": "2026-07-01"}).json() == []


def test_list_rejects_malformed_date(client):
    assert client.get("/api/meals", params={"date": "garbage"}).status_code == 422
    assert client.get("/api/meals", params={"date": "2026-13-40"}).status_code == 422


def test_undated_list_is_capped_and_newest_first(client):
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        client.post("/api/meals", json=_sample(date=day, name=f"Meal {day}"))

    meals = client.get("/api/meals", params={"limit": 2}).json()
    assert [m["date"] for m in meals] == ["2026-07-03", "2026-07-02"]
    assert client.get("/api/meals", params={"limit": 0}).status_code == 422
    assert client.get("/api/meals", params={"limit": 5000}).status_code == 422
