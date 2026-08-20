"""GET /api/settings/targets, and the targets_auto write-back.

The arithmetic itself is covered in test_calculations.py. What is tested here
is the wiring: what the endpoint reports when the profile is incomplete, and
the two paths that rewrite the stored goals.
"""
from datetime import date, timedelta

import pytest

BASE_SETTINGS = {
    "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
    "fat_goal": 70, "track_carbs": True, "track_fat": True,
}

FULL_PROFILE = {
    "height_cm": 180.0,
    "birth_date": "1990-05-04",
    "sex": "male",
    "activity_level": "moderate",
    "goal_rate_kg_per_week": -0.5,
}


def set_profile(client, **overrides):
    body = {**BASE_SETTINGS, **FULL_PROFILE, **overrides}
    response = client.put("/api/settings", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def weigh_in(client, weight_kg, days_ago=0):
    day = date.today() - timedelta(days=days_ago)
    response = client.post(
        "/api/weights", json={"date": day.isoformat(), "weight_kg": weight_kg}
    )
    assert response.status_code == 200, response.text
    return response.json()


def log_meal(client, calories, days_ago, name="Seeded"):
    day = date.today() - timedelta(days=days_ago)
    response = client.post(
        "/api/meals",
        json={
            "date": day.isoformat(),
            "name": name,
            "calories": calories,
            "protein": 100.0,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def seed_measurable_history(
    client, days=20, calories=2700.0, start_kg=80.0, kg_per_week=0.0
):
    """A window dense enough to measure: a weigh-in and a meal on every day.

    Ends *yesterday*, deliberately, so a test can add today separately and
    observe whether today leaks into the measurement.
    """
    for days_ago in range(1, days + 1):
        elapsed_weeks = (days - days_ago) / 7.0
        weigh_in(client, start_kg + kg_per_week * elapsed_weeks, days_ago=days_ago)
        log_meal(client, calories, days_ago=days_ago)


def targets(client):
    response = client.get("/api/settings/targets")
    assert response.status_code == 200, response.text
    return response.json()


def test_targets_names_everything_missing_on_a_fresh_account(client):
    """An empty profile is an ordinary state, so this is a 200 with reasons."""
    body = client.get("/api/settings/targets").json()

    assert body["missing"] == [
        "weight", "height_cm", "birth_date", "sex",
        "activity_level", "goal_rate_kg_per_week",
    ]
    assert body["target_calories"] is None
    assert body["bmi"] is None


def test_bmi_appears_before_the_rest_of_the_profile_does(client):
    """BMI needs two of the six fields, so it is the first number to show up.

    Withholding it until the whole profile is filled in would mean a new user
    who has logged one weigh-in and their height sees nothing at all.
    """
    set_profile(client, birth_date=None, sex=None, activity_level=None,
                goal_rate_kg_per_week=None)
    weigh_in(client, 80)

    body = client.get("/api/settings/targets").json()
    assert body["bmi"] == 24.7
    assert body["target_calories"] is None
    assert "height_cm" not in body["missing"]
    assert "sex" in body["missing"]


def test_targets_are_computed_once_the_profile_is_complete(client):
    set_profile(client)
    weigh_in(client, 80)

    body = client.get("/api/settings/targets").json()
    assert body["missing"] == []
    # 10(80) + 6.25(180) - 5(36) + 5 = 1750 for a user born 1990-05-04, then
    # x1.55 for "moderate" = 2712.5, then -550/day for -0.5 kg/week.
    assert body["bmr"] > 1700
    assert body["tdee"] > body["bmr"]
    assert body["target_calories"] < body["tdee"]
    assert body["clamped_reason"] is None


def test_the_weight_used_is_reported_with_the_date_it_was_logged(client):
    """No derived number reaches the UI without its inputs beside it.

    Body weight is the input most likely to be quietly stale, so the endpoint
    hands back which weigh-in it used rather than only what it concluded.
    """
    set_profile(client)
    weigh_in(client, 82, days_ago=3)

    body = client.get("/api/settings/targets").json()
    assert body["weight_kg"] == 82
    assert body["weight_date"] == (date.today() - timedelta(days=3)).isoformat()


def test_a_stale_weigh_in_does_not_silently_drive_a_target(client):
    """Deriving today's calories from a weight six months old is a wrong answer
    that looks exactly like a right one."""
    set_profile(client)
    weigh_in(client, 80, days_ago=200)

    body = client.get("/api/settings/targets").json()
    assert "weight" in body["missing"]
    assert body["target_calories"] is None


def test_an_over_ambitious_rate_is_answered_with_an_explanation(client):
    set_profile(client, goal_rate_kg_per_week=-3)
    weigh_in(client, 80)

    body = client.get("/api/settings/targets").json()
    assert body["clamped_reason"] is not None
    assert "Rate limited" in body["clamped_reason"]


def test_targets_auto_rewrites_the_goals_on_save(client):
    saved = set_profile(client)
    weigh_in(client, 80)
    assert saved["calorie_goal"] == 2000  # still manual at this point

    saved = set_profile(client, targets_auto=True)
    targets = client.get("/api/settings/targets").json()
    assert saved["calorie_goal"] == targets["target_calories"]
    assert saved["protein_goal"] == targets["protein_g"]
    assert saved["carbs_goal"] == targets["carbs_g"]
    assert saved["fat_goal"] == targets["fat_g"]


def test_targets_auto_ignores_the_goals_the_client_submits(client):
    """The goal inputs are read-only in the UI, but the server is the enforcer."""
    set_profile(client)
    weigh_in(client, 80)
    saved = set_profile(client, targets_auto=True, calorie_goal=9999)
    assert saved["calorie_goal"] != 9999


def test_a_weigh_in_moves_an_auto_target(client):
    """Otherwise the target lags the weight by however long it takes the user
    to next open Settings — the static-number problem this feature exists for."""
    set_profile(client)
    weigh_in(client, 90)
    heavier = set_profile(client, targets_auto=True)["calorie_goal"]

    weigh_in(client, 80)
    lighter = client.get("/api/settings").json()["calorie_goal"]

    assert lighter < heavier


def test_a_weigh_in_leaves_manual_goals_alone(client):
    set_profile(client, targets_auto=False, calorie_goal=2345)
    weigh_in(client, 80)
    assert client.get("/api/settings").json()["calorie_goal"] == 2345


def test_targets_auto_stays_on_when_the_profile_is_incomplete(client):
    """Switching it off behind the user's back would be a silent decision.

    The flag stays set and starts working the moment the missing field lands.
    """
    saved = set_profile(client, targets_auto=True, height_cm=None)
    assert saved["targets_auto"] is True
    assert saved["calorie_goal"] == 2000  # untouched, not zeroed

    weigh_in(client, 80)
    saved = set_profile(client, targets_auto=True)
    assert saved["calorie_goal"] != 2000


def test_turning_auto_off_leaves_the_computed_goals_editable(client):
    set_profile(client)
    weigh_in(client, 80)
    computed = set_profile(client, targets_auto=True)["calorie_goal"]

    saved = set_profile(client, targets_auto=False, calorie_goal=computed)
    assert saved["targets_auto"] is False
    saved = set_profile(client, targets_auto=False, calorie_goal=1234)
    assert saved["calorie_goal"] == 1234


def test_targets_requires_authentication(anon_client):
    assert anon_client.get("/api/settings/targets").status_code == 401


# --- measured TDEE wiring -----------------------------------------------------


def test_a_dense_history_is_measured_rather_than_estimated(client):
    set_profile(client)
    seed_measurable_history(client)

    body = targets(client)

    assert body["tdee_source"] == "measured"
    assert body["tdee_basis"]["unavailable_reason"] is None
    assert body["tdee_basis"]["logged_days"] == 20
    assert body["tdee_basis"]["weigh_ins"] == 20


def test_a_stable_weight_measures_tdee_as_the_intake_that_held_it(client):
    """The definition, end to end: eat 2700 and hold weight, and you burn 2700."""
    set_profile(client)
    seed_measurable_history(client, calories=2700.0, kg_per_week=0.0)

    body = targets(client)

    assert body["tdee_source"] == "measured"
    assert body["tdee"] == pytest.approx(2700, abs=5)


def test_the_formula_estimate_is_kept_even_once_measurement_wins(client):
    """Both numbers travel, so the card can show them side by side.

    Agreement is reassuring and divergence is diagnostic; neither is visible if
    the estimate is thrown away the moment it stops driving the target.
    """
    set_profile(client)
    seed_measurable_history(client)

    body = targets(client)

    assert body["tdee_source"] == "measured"
    assert body["tdee_estimated"] is not None
    assert body["tdee_estimated"] != body["tdee"]


def test_todays_partial_logging_cannot_move_a_measured_tdee(client):
    """Regression: the 223 kcal error found against real data.

    Today is a half-logged day -- breakfast in, dinner not yet -- so averaging
    it in as a finished day understates intake, which understates the measured
    burn, which tells the user to eat less. Against the live account this moved
    a 14-day TDEE from 2589 to 2366 kcal. Same class as the Phase 0.6 dashboard
    bug, and worse here because the number drives a target rather than a chart.

    It also closes a feedback loop: if today's meals moved today's target, the
    goal would rise as the user ate towards it.
    """
    set_profile(client)
    seed_measurable_history(client)
    before = targets(client)

    # A deliberately tiny partial day, plus this morning's weigh-in.
    log_meal(client, 300.0, days_ago=0, name="Just breakfast")
    weigh_in(client, 80.0, days_ago=0)

    after = targets(client)

    assert after["tdee"] == before["tdee"]
    assert after["tdee_basis"]["mean_intake"] == before["tdee_basis"]["mean_intake"]


def test_too_few_weigh_ins_falls_back_without_calling_the_profile_incomplete(client):
    """Falling back is not a failure -- the user still gets a working target.

    So `missing` must stay empty: listing the shortfall there would make a
    complete profile read as incomplete forever, and the UI would ask for a
    field the user has already filled in.
    """
    set_profile(client)
    for days_ago in range(1, 21):
        log_meal(client, 2700.0, days_ago=days_ago)
    weigh_in(client, 80.0, days_ago=1)

    body = targets(client)

    assert body["tdee_source"] == "estimated"
    assert body["missing"] == []
    assert body["target_calories"] is not None
    assert body["tdee_basis"]["unavailable_reason"] is not None
    assert "Weigh in on" in body["tdee_basis"]["unavailable_reason"]


def test_a_refusal_still_reports_the_meals_that_were_logged(client):
    """A count that is wrong in the payload is wrong even if no card draws it.

    This account logged meals every day for three weeks and simply has not
    weighed in. Reporting `logged_days: 0` at them because the weigh-in guard
    fired first would be a number that contradicts what they actually did.
    """
    set_profile(client)
    for days_ago in range(1, 21):
        log_meal(client, 2700.0, days_ago=days_ago)
    weigh_in(client, 80.0, days_ago=1)

    basis = targets(client)["tdee_basis"]

    assert basis["unavailable_reason"] is not None
    assert basis["logged_days"] == 20


def test_a_short_span_of_weigh_ins_is_refused_with_its_own_reason(client):
    """Enough weigh-ins, too few days between them: the slope is noise.

    Ten weigh-ins crammed into ten days produced 2700 kcal against a formula
    estimate of 2498 on real data, because trend weight had moved -0.01 kg.
    """
    set_profile(client)
    for days_ago in range(1, 11):
        weigh_in(client, 80.0, days_ago=days_ago)
        log_meal(client, 2700.0, days_ago=days_ago)

    body = targets(client)

    assert body["tdee_source"] == "estimated"
    assert "at least" in body["tdee_basis"]["unavailable_reason"]


def test_sparse_meal_logging_is_refused_even_with_daily_weigh_ins(client):
    """The average stands in for unlogged days, so too few of them is a guess."""
    set_profile(client)
    for days_ago in range(1, 21):
        weigh_in(client, 80.0, days_ago=days_ago)
    for days_ago in range(1, 6):
        log_meal(client, 2700.0, days_ago=days_ago)

    body = targets(client)

    assert body["tdee_source"] == "estimated"
    assert "logged meals on" in body["tdee_basis"]["unavailable_reason"]


def test_an_incomplete_profile_reports_no_basis_at_all(client):
    """`missing` is still the answer when the profile itself is the blocker."""
    set_profile(client, height_cm=None)
    seed_measurable_history(client)

    body = targets(client)

    assert "height_cm" in body["missing"]
    assert body["tdee_basis"] is None


def test_a_measured_tdee_drives_the_auto_written_goals(client):
    """The point of the phase: the stored goals come from the measurement."""
    set_profile(client, targets_auto=True)
    seed_measurable_history(client, calories=2700.0, kg_per_week=0.0)

    body = targets(client)
    stored = client.get("/api/settings").json()

    assert body["tdee_source"] == "measured"
    assert stored["calorie_goal"] == pytest.approx(body["target_calories"], abs=1)
