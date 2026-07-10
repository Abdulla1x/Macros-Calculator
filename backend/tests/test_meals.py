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
