def _add_meal(client, date, calories, protein, carbs=None, fat=None):
    client.post("/api/meals", json={
        "date": date, "name": "meal", "calories": calories,
        "protein": protein, "carbs": carbs, "fat": fat,
    })


def test_daily_summary_totals_and_averages(client):
    _add_meal(client, "2026-07-01", 500, 40, carbs=50)
    _add_meal(client, "2026-07-01", 300, 20, carbs=30)
    _add_meal(client, "2026-07-02", 600, 50)

    summary = client.get("/api/analytics/daily").json()
    assert len(summary["days"]) == 2
    assert summary["days"][0] == {
        "date": "2026-07-01", "calories": 800, "protein": 60, "carbs": 80, "fat": None,
    }
    assert summary["totals"]["calories"] == 1400
    assert summary["averages"]["calories"] == 700
    # carbs average only over days that have carbs data
    assert summary["averages"]["carbs"] == 80


def test_daily_summary_range_filter(client):
    _add_meal(client, "2026-06-30", 100, 10)
    _add_meal(client, "2026-07-01", 200, 20)
    _add_meal(client, "2026-07-05", 300, 30)

    summary = client.get(
        "/api/analytics/daily", params={"start": "2026-07-01", "end": "2026-07-04"}
    ).json()
    assert [day["date"] for day in summary["days"]] == ["2026-07-01"]


def test_settings_defaults_and_update(client):
    defaults = client.get("/api/settings").json()
    assert defaults == {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }

    updated = {
        "calorie_goal": 2400, "protein_goal": 180, "carbs_goal": 300,
        "fat_goal": 80, "track_carbs": True, "track_fat": False,
    }
    assert client.put("/api/settings", json=updated).json() == updated
    assert client.get("/api/settings").json() == updated
