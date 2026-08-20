from conftest import put_raw_json


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
    assert summary["logged_days"] == 2
    # Every macro averages over the same denominator (days with meals), so a
    # macro logged on only some days is not inflated: carbs appear on one of
    # the two days, and 80 / 2 is reported rather than 80 / 1.
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


def test_daily_summary_averages_ignore_unlogged_days_in_range(client):
    """An unlogged day is missing data, not a day of zero intake.

    Dividing by calendar days would report 200 kcal/day for someone who ate
    800 on the one day they logged — understating intake by however many days
    they forgot, with nothing on screen to say so.
    """
    _add_meal(client, "2026-07-01", 800, 60)

    summary = client.get(
        "/api/analytics/daily", params={"start": "2026-07-01", "end": "2026-07-04"}
    ).json()
    assert summary["averages"]["calories"] == 800
    assert summary["logged_days"] == 1


def test_daily_summary_average_is_unchanged_by_widening_an_empty_range(client):
    """Regression: the dashboard's 7-day window starts a day before the data.

    Reported from the live app — asking for 07-26..08-01 with nothing on 07-26
    reported 2040 kcal/day where the six logged days averaged 2380.
    """
    for day, calories in [("2026-07-27", 2100), ("2026-07-28", 2300)]:
        _add_meal(client, day, calories, 100)

    tight = client.get(
        "/api/analytics/daily", params={"start": "2026-07-27", "end": "2026-07-28"}
    ).json()
    padded = client.get(
        "/api/analytics/daily", params={"start": "2026-07-20", "end": "2026-07-28"}
    ).json()
    assert tight["averages"] == padded["averages"]
    assert padded["averages"]["calories"] == 2200
    assert padded["logged_days"] == 2


def test_settings_defaults_and_update(client):
    defaults = client.get("/api/settings").json()
    assert defaults == {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "weight_unit": "kg",
    }

    updated = {
        "calorie_goal": 2400, "protein_goal": 180, "carbs_goal": 300,
        "fat_goal": 80, "track_carbs": True, "track_fat": False,
        "weight_unit": "lb",
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


def test_settings_reject_non_finite_goals(client):
    """`gt=0` admits infinity, and a goal is a divisor.

    Every progress ring on the dashboard divides today's total by one of these,
    so an infinite goal renders as permanent 0% — and GET /api/settings would
    hand back `null` for a field types.ts types as `number`.
    """
    valid = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    for field in ("calorie_goal", "protein_goal", "carbs_goal", "fat_goal"):
        response = put_raw_json(
            client, "/api/settings", {**valid, field: float("inf")}
        )
        assert response.status_code == 422, f"{field}=inf was accepted"


def test_weight_unit_defaults_so_older_clients_still_save(client):
    """A PUT written before weight_unit existed must not start 422-ing."""
    legacy_body = {
        "calorie_goal": 2100, "protein_goal": 170, "carbs_goal": 260,
        "fat_goal": 75, "track_carbs": False, "track_fat": True,
    }
    response = client.put("/api/settings", json=legacy_body)
    assert response.status_code == 200
    assert response.json()["weight_unit"] == "kg"


def test_weight_unit_rejects_unknown_units(client):
    valid = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    for bad in ("stone", "KG", ""):
        response = client.put("/api/settings", json={**valid, "weight_unit": bad})
        assert response.status_code == 422, f"{bad!r} was accepted"
