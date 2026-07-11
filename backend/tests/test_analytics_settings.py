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
    # Every macro averages over the same denominator (days in range), so a
    # macro logged on only some days is not inflated.
    assert summary["averages"]["carbs"] == 40


def test_daily_summary_range_filter(client):
    _add_meal(client, "2026-06-30", 100, 10)
    _add_meal(client, "2026-07-01", 200, 20)
    _add_meal(client, "2026-07-05", 300, 30)

    summary = client.get(
        "/api/analytics/daily", params={"start": "2026-07-01", "end": "2026-07-04"}
    ).json()
    assert [day["date"] for day in summary["days"]] == ["2026-07-01"]


def test_daily_summary_empty_when_no_meals(client):
    summary = client.get("/api/analytics/daily").json()
    assert summary["days"] == []
    assert summary["averages"] == {
        "calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0,
    }


def test_daily_summary_rejects_inverted_range(client):
    response = client.get(
        "/api/analytics/daily", params={"start": "2026-07-10", "end": "2026-07-01"}
    )
    assert response.status_code == 422


def test_daily_summary_averages_count_unlogged_days_in_range(client):
    _add_meal(client, "2026-07-01", 800, 60)

    summary = client.get(
        "/api/analytics/daily", params={"start": "2026-07-01", "end": "2026-07-04"}
    ).json()
    # One logged day out of four in range → the average reflects all four.
    assert summary["averages"]["calories"] == 200


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


def test_settings_reject_non_positive_goals(client):
    valid = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    for field in ("calorie_goal", "protein_goal", "carbs_goal", "fat_goal"):
        for bad in (-100, 0):
            response = client.put("/api/settings", json={**valid, field: bad})
            assert response.status_code == 422, f"{field}={bad} was accepted"
