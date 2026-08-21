"""Step logging: the three verbs, the per-day upsert, and the input bounds.

Dates are relative to today because the POST validator rejects future dates, so
a fixed calendar date would eventually start failing on its own -- the same
reason test_water.py and test_weights.py do it.
"""
from datetime import date, timedelta
from pathlib import Path

from app.routers import steps as app_steps
from app.calculations import KCAL_PER_STEP_PER_KG
from conftest import post_raw_json


def days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def save(client, steps: int, day: str | None = None):
    return client.post(
        "/api/steps", json={"date": day or date.today().isoformat(), "steps": steps}
    )


# PUT /api/settings replaces the four goals and the two toggles, so they are
# required on every call. Sending only the field under test is a 422 about the
# missing goals, which would make a bounds test pass without ever reaching the
# bound.
BASE_SETTINGS = {
    "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
    "fat_goal": 70, "track_carbs": False, "track_fat": False,
}


def put_settings(client, **fields):
    return client.put("/api/settings", json={**BASE_SETTINGS, **fields})


def test_save_read_and_clear(client):
    created = save(client, 8000)
    assert created.status_code == 200
    assert created.json()["steps"] == 8000

    day = client.get("/api/steps").json()
    assert day["steps"] == 8000
    assert day["logged"] is True

    assert client.delete("/api/steps").status_code == 204
    after = client.get("/api/steps").json()
    assert after["steps"] == 0
    assert after["logged"] is False


def test_a_second_save_for_a_day_replaces_the_first(client):
    """The difference from /api/water, pinned.

    A second glass of water is a second glass; a second reading of the
    pedometer is the same day's walking, counted later. If this table ever
    loses its unique index on (user_id, date) this is the test that fails.
    """
    save(client, 4000)
    save(client, 9500)

    day = client.get("/api/steps").json()
    assert day["steps"] == 9500

    # And it is one row, not two summed into a plausible-looking total.
    export = client.get("/api/data/export/all").json()
    assert len(export["steps"]) == 1


def test_a_day_with_nothing_logged_is_200_not_404(client):
    day = client.get("/api/steps", params={"date": days_ago(3)}).json()
    assert day["steps"] == 0
    assert day["logged"] is False
    assert day["burn_kcal"] is None


def test_a_logged_zero_is_not_the_same_as_an_unlogged_day(client):
    """Why StepDay carries `logged` at all.

    Zero is a legal count -- a day with no walking is a real day, and a
    mistyped count has to be correctable down to zero. Both states report
    `steps == 0`, so without this flag the card could not tell which one it is
    looking at, and would offer to clear a day that has nothing in it.
    """
    assert save(client, 0).status_code == 200
    day = client.get("/api/steps").json()
    assert day["steps"] == 0
    assert day["logged"] is True


def test_days_are_scoped_to_their_date(client):
    save(client, 3000, days_ago(2))
    save(client, 7000)

    assert client.get("/api/steps", params={"date": days_ago(2)}).json()["steps"] == 3000
    assert client.get("/api/steps").json()["steps"] == 7000


def test_clearing_a_day_that_was_never_logged_is_404(client):
    assert client.delete("/api/steps", params={"date": days_ago(5)}).status_code == 404


def test_no_goal_until_one_is_set(client):
    save(client, 6000)
    assert client.get("/api/steps").json()["goal"] is None

    assert put_settings(client, steps_goal=9000).status_code == 200
    assert client.get("/api/steps").json()["goal"] == 9000

    # Cleared back to no goal, not back to a shipped default -- there isn't one.
    assert put_settings(client, steps_goal=None).status_code == 200
    assert client.get("/api/steps").json()["goal"] is None


def test_the_burn_estimate_needs_a_weigh_in(client):
    save(client, 10000)
    assert client.get("/api/steps").json()["burn_kcal"] is None

    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 70.0})
    day = client.get("/api/steps").json()
    assert day["burn_weight_kg"] == 70.0
    assert day["burn_kcal"] == round(KCAL_PER_STEP_PER_KG * 70.0 * 10000, 1)


def test_steps_router_never_recomputes_targets():
    """Phase 5's guarantee, defended at the source rather than the behaviour.

    The sibling of test_water.py's version, and needed more here: this router
    copies the upsert body of routers/weights.py, which *does* call
    apply_auto_targets, so bringing the call along is a copy-paste away rather
    than an invention.

    A value-level test cannot do this job. Steps are not an input to any
    target, so calling apply_auto_targets here would recompute the goals and
    land on exactly the same numbers -- "never called" and "called, no change
    today" are indistinguishable from outside, right up until something makes
    them differ.

    Why it matters: a measured TDEE already contains the energy spent on every
    step inside its measurement window, so a step-derived burn added on top
    double-counts; and that window stops at *yesterday* precisely so what you
    log today cannot move the goal you are eating towards today.
    """
    source = Path(app_steps.__file__).read_text()
    body = source.split('"""', 2)[2]  # skip the module docstring, which names it
    assert "apply_auto_targets" not in body


def test_logging_steps_leaves_the_stored_goals_alone(client):
    """The observable half of the rule above. Weaker, and kept for that reason.

    It passes whether or not the call exists, because recomputing lands on the
    same answer. What it does catch is a future change that makes steps an
    input to a target without anyone noticing the rule above.
    """
    put_settings(
        client,
        height_cm=180.0, birth_date="1990-05-04", sex="male",
        activity_level="moderate", goal_rate_kg_per_week=-0.5,
        targets_auto=True,
    )
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 80.0})
    before = client.get("/api/settings").json()

    save(client, 15000)

    assert client.get("/api/settings").json() == before


def test_a_zero_is_accepted_but_a_negative_count_is_not(client):
    assert save(client, 0).status_code == 200
    assert save(client, -1).status_code == 422


def test_an_implausible_count_is_refused(client):
    assert save(client, 200_001).status_code == 422


def test_a_fractional_count_is_refused(client):
    """A step is a thing you either took or did not."""
    assert save(client, 8000.5).status_code == 422


def test_a_non_finite_count_is_refused(client):
    response = post_raw_json(
        client, "/api/steps", f'{{"date": "{date.today().isoformat()}", "steps": 1e999}}'
    )
    assert response.status_code == 422


def test_a_future_date_is_refused(client):
    future = (date.today() + timedelta(days=30)).isoformat()
    assert save(client, 5000, future).status_code == 422


def test_a_goal_out_of_range_is_refused(client):
    """Through a complete body, so the 422 is about the goal and nothing else."""
    assert put_settings(client, steps_goal=0).status_code == 422
    assert put_settings(client, steps_goal=200_001).status_code == 422
    # And the bound is the only thing rejecting it -- the same body passes.
    assert put_settings(client, steps_goal=200_000).status_code == 200
