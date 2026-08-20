"""GET /api/settings/targets, and the targets_auto write-back.

The arithmetic itself is covered in test_calculations.py. What is tested here
is the wiring: what the endpoint reports when the profile is incomplete, and
the two paths that rewrite the stored goals.
"""
from datetime import date, timedelta

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
