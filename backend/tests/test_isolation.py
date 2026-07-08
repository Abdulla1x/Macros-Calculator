"""Cross-tenant isolation: two users must never see or modify each other's data."""
from tests.test_meal_ai import SAMPLE, configure

MEAL_A = {"date": "2026-07-01", "name": "Alpha Meal", "calories": 500, "protein": 40}
MEAL_B = {"date": "2026-07-01", "name": "Beta Meal", "calories": 300, "protein": 20}
FOOD_A = {"name": "Shared Name Food", "serving_size": 100, "calories": 165, "protein": 31}


def test_meal_lists_are_scoped(client, client_b):
    a_meal = client.post("/api/meals", json=MEAL_A).json()
    client_b.post("/api/meals", json=MEAL_B)

    a_names = [m["name"] for m in client.get("/api/meals").json()]
    b_names = [m["name"] for m in client_b.get("/api/meals").json()]
    assert a_names == ["Alpha Meal"]
    assert b_names == ["Beta Meal"]

    # Date-filtered listing is scoped too.
    b_today = client_b.get("/api/meals", params={"date": "2026-07-01"}).json()
    assert [m["name"] for m in b_today] == ["Beta Meal"]
    assert all(m["id"] != a_meal["id"] for m in b_today)


def test_cannot_delete_another_users_meal(client, client_b):
    a_meal = client.post("/api/meals", json=MEAL_A).json()

    assert client_b.delete(f"/api/meals/{a_meal['id']}").status_code == 404
    # A's meal is untouched.
    assert [m["id"] for m in client.get("/api/meals").json()] == [a_meal["id"]]


def test_food_library_is_scoped(client, client_b):
    a_food = client.post("/api/foods", json=FOOD_A).json()

    assert client_b.get("/api/foods").json() == []
    assert client_b.get("/api/foods/search", params={"q": "Shared"}).json() == []
    assert client_b.delete(f"/api/foods/{a_food['id']}").status_code == 404
    assert [f["id"] for f in client.get("/api/foods").json()] == [a_food["id"]]


def test_same_food_name_allowed_per_user_and_upsert_stays_scoped(client, client_b):
    client.post("/api/foods", json=FOOD_A)
    # B can own a food with the identical (case-insensitive) name.
    b_food = client_b.post(
        "/api/foods", json={**FOOD_A, "name": "shared name food", "calories": 999}
    )
    assert b_food.status_code == 201

    # B's save was an insert into B's library, not an update of A's row.
    a_food = client.get("/api/foods").json()[0]
    assert a_food["calories"] == 165
    assert client_b.get("/api/foods").json()[0]["calories"] == 999
    assert a_food["id"] != b_food.json()["id"]


def test_settings_are_independent(client, client_b):
    client.put("/api/settings", json={
        "calorie_goal": 1800, "protein_goal": 160, "carbs_goal": 180,
        "fat_goal": 60, "track_carbs": True, "track_fat": True,
    })
    b_settings = client_b.get("/api/settings").json()
    assert b_settings["calorie_goal"] == 2000  # untouched defaults
    assert b_settings["track_carbs"] is False
    assert client.get("/api/settings").json()["calorie_goal"] == 1800


def test_analytics_only_count_own_meals(client, client_b):
    client.post("/api/meals", json=MEAL_A)
    client_b.post("/api/meals", json=MEAL_B)

    a_summary = client.get("/api/analytics/daily").json()
    b_summary = client_b.get("/api/analytics/daily").json()
    assert a_summary["totals"]["calories"] == 500
    assert b_summary["totals"]["calories"] == 300


def test_csv_export_only_contains_own_meals(client, client_b):
    client.post("/api/meals", json=MEAL_A)
    client_b.post("/api/meals", json=MEAL_B)

    b_export = client_b.get("/api/data/export").text
    assert "Beta Meal" in b_export
    assert "Alpha Meal" not in b_export


def test_csv_import_is_scoped_and_duplicates_dont_cross_users(client, client_b):
    client.post("/api/meals", json=MEAL_A)

    # A row identical to A's meal is NOT a duplicate for B.
    csv_content = "date,name,calories,protein\n2026-07-01,Alpha Meal,500,40\n"
    result = client_b.post(
        "/api/data/import", files={"file": ("import.csv", csv_content, "text/csv")}
    ).json()
    assert result["inserted"] == 1
    assert result["skipped_duplicates"] == 0

    # ...but it IS a duplicate for A.
    result_a = client.post(
        "/api/data/import", files={"file": ("import.csv", csv_content, "text/csv")}
    ).json()
    assert result_a["skipped_duplicates"] == 1

    # B's import landed in B's account only; A still has exactly one meal.
    assert len(client.get("/api/meals").json()) == 1


def test_ai_analysis_link_is_double_scoped(client, client_b, monkeypatch):
    configure(monkeypatch)
    a_analysis = client.post("/api/ai/analyze", data={"text": "chicken"}).json()
    a_meal = client.post("/api/meals", json=MEAL_A).json()
    b_meal = client_b.post("/api/meals", json=MEAL_B).json()

    # B cannot link A's analysis to anything.
    assert client_b.patch(
        f"/api/ai/analyses/{a_analysis['analysis_id']}", json={"meal_id": b_meal["id"]}
    ).status_code == 404

    # A cannot link their analysis to B's meal.
    assert client.patch(
        f"/api/ai/analyses/{a_analysis['analysis_id']}", json={"meal_id": b_meal["id"]}
    ).status_code == 404

    # The legitimate link still works.
    assert client.patch(
        f"/api/ai/analyses/{a_analysis['analysis_id']}", json={"meal_id": a_meal["id"]}
    ).status_code == 204


def test_ai_daily_quota_is_per_user(client, client_b, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("AI_DAILY_LIMIT", "2")

    assert client.post("/api/ai/analyze", data={"text": "one"}).status_code == 200
    assert client.post("/api/ai/analyze", data={"text": "two"}).status_code == 200
    blocked = client.post("/api/ai/analyze", data={"text": "three"})
    assert blocked.status_code == 429
    assert "limit" in blocked.json()["detail"].lower()

    # B's quota is unaffected by A exhausting theirs.
    assert client_b.post("/api/ai/analyze", data={"text": "b-one"}).status_code == 200
