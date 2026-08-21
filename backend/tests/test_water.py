"""Water logging: the three verbs, the derived goal, and the input bounds.

Dates are relative to today because the POST validator rejects future dates, so
a fixed calendar date would eventually start failing on its own -- the same
reason test_weights.py does it.
"""
from datetime import date, timedelta
from pathlib import Path

from app.routers import water as app_water
from app.calculations import (
    WATER_DEFAULT_GOAL_ML,
    WATER_ML_PER_KG,
)
from conftest import post_raw_json


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def add(client, ml: float, day: str | None = None):
    return client.post(
        "/api/water", json={"date": day or date.today().isoformat(), "ml": ml}
    )


def test_add_list_total_and_delete(client):
    created = add(client, 250)
    assert created.status_code == 201
    first_id = created.json()["id"]
    add(client, 500)

    day = client.get("/api/water").json()
    assert day["total_ml"] == 750
    # Newest first, so the client's undo button is entries[0] with no sorting.
    assert [e["ml"] for e in day["entries"]] == [500, 250]

    assert client.delete(f"/api/water/{first_id}").status_code == 204
    assert client.get("/api/water").json()["total_ml"] == 500


def test_two_entries_on_one_day_both_survive(client):
    """The difference from /api/weights, pinned.

    A second weigh-in for a date replaces the first; a second glass of water is
    a second glass. If this table ever grows a unique index on (user_id, date)
    this is the test that should fail.
    """
    add(client, 250)
    add(client, 250)
    day = client.get("/api/water").json()
    assert len(day["entries"]) == 2
    assert day["total_ml"] == 500


def test_a_day_with_nothing_logged_is_200_not_404(client):
    day = client.get("/api/water", params={"date": days_ago(3)}).json()
    assert day["total_ml"] == 0
    assert day["entries"] == []
    # The goal is still answered: the card renders an empty ring, not an error.
    assert day["goal_ml"] > 0


def test_entries_are_scoped_to_the_requested_date(client):
    add(client, 250, days_ago(1))
    add(client, 500)
    assert client.get("/api/water", params={"date": days_ago(1)}).json()["total_ml"] == 250
    assert client.get("/api/water").json()["total_ml"] == 500


def test_goal_falls_back_to_the_default_without_a_weigh_in(client):
    day = client.get("/api/water").json()
    assert day["goal_ml"] == WATER_DEFAULT_GOAL_ML
    # Stated, not disguised: the UI uses this to ask for a weigh-in rather than
    # present a folk figure as if it were personal.
    assert day["goal_basis"]["source"] == "default"
    assert day["goal_basis"]["weight_kg"] is None


def test_goal_is_derived_from_trend_weight_once_there_is_one(client):
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 70.0})
    day = client.get("/api/water").json()
    assert day["goal_basis"]["source"] == "weight"
    assert day["goal_basis"]["ml_per_kg"] == WATER_ML_PER_KG
    assert day["goal_basis"]["weight_kg"] == 70.0
    # 35 ml/kg x 70 kg, rounded to the nearest 50.
    assert day["goal_ml"] == 2450


def test_a_custom_goal_overrides_the_derivation(client):
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 70.0})
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "water_goal_ml": 3000})

    day = client.get("/api/water").json()
    assert day["goal_ml"] == 3000
    assert day["goal_basis"]["source"] == "custom"
    # No weight is reported, because none was consulted -- the caption for a
    # custom goal has nothing to explain.
    assert day["goal_basis"]["weight_kg"] is None


def test_clearing_a_custom_goal_returns_to_the_derivation(client):
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 70.0})
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "water_goal_ml": 3000})
    client.put("/api/settings", json={**settings, "water_goal_ml": None})

    day = client.get("/api/water").json()
    assert day["goal_basis"]["source"] == "weight"
    assert day["goal_ml"] == 2450


def test_water_router_never_recomputes_targets():
    """Phase 5's guarantee, defended at the source rather than the behaviour.

    A value-level test cannot do this job, and it is worth saying why: water is
    not an input to any target, so calling apply_auto_targets from this router
    would recompute the goals and arrive at exactly the same numbers. "Never
    called" and "called, no change today" are indistinguishable from outside --
    right up until a later phase makes them differ.

    So this asserts the call is absent. It reads as crude and it is the only
    form that actually holds: it catches both `from ..targets import
    apply_auto_targets` and `targets.apply_auto_targets(...)`, where a spy
    patched onto app.targets would miss the first.

    Why it matters: water weight is precisely the day-to-day noise weight_trend
    exists to smooth away, and a measured TDEE stops at *yesterday* so that
    what you log today cannot move the goal you are eating towards today. One
    convenient call here reopens both.
    """
    source = Path(app_water.__file__).read_text()
    body = source.split('"""', 2)[2]  # skip the module docstring, which names it
    assert "apply_auto_targets" not in body


def test_logging_water_leaves_the_stored_goals_alone(client):
    """The observable half of the rule above. Weaker, and kept for that reason:
    it is what a user would actually notice if the guarantee broke in a phase
    where water *had* become an input to something."""
    client.put("/api/settings", json={
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
        "activity_level": "moderate", "targets_auto": True,
    })
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 80.0})
    before = client.get("/api/settings").json()

    for _ in range(6):
        add(client, 500)

    assert client.get("/api/settings").json() == before


def test_bounds_and_bad_input_are_refused(client):
    assert add(client, 0).status_code == 422
    assert add(client, -250).status_code == 422
    # MAX_WATER_ENTRY_ML is 5000.
    assert add(client, 5001).status_code == 422
    assert add(client, 5000).status_code == 201
    # The upper bound is what closes inf, so this must 422 rather than store.
    assert post_raw_json(
        client, "/api/water", {"date": date.today().isoformat(), "ml": float("inf")}
    ).status_code == 422


def test_a_future_date_is_refused(client):
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    assert add(client, 250, tomorrow).status_code == 422


def test_deleting_a_missing_entry_is_404(client):
    assert client.delete("/api/water/999999").status_code == 404
