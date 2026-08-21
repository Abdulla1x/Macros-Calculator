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


# An account that has never opened Settings. Spelled out once because several
# tests below assert against the whole payload, and a field missing from the
# response is exactly the kind of regression those assertions exist to catch.
# Every optional settings field in its unset state. Shared because several
# tests below compare the *whole* payload, and a new column would otherwise
# break each of them in a different place.
#
# Named for the behaviour rather than the feature it started as: this was the
# body profile alone, and it now carries water too. Anything added to the
# patched group in routers/settings.py belongs here.
UNSET_OPTIONALS = {
    "height_cm": None, "birth_date": None, "sex": None,
    "activity_level": None, "goal_rate_kg_per_week": None,
    "targets_auto": False,
    "water_goal_ml": None, "water_quick_adds": None,
    "steps_goal": None,
}


def test_settings_defaults_and_update(client):
    defaults = client.get("/api/settings").json()
    assert defaults == {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "weight_unit": "kg", **UNSET_OPTIONALS,
    }

    updated = {
        "calorie_goal": 2400, "protein_goal": 180, "carbs_goal": 300,
        "fat_goal": 80, "track_carbs": True, "track_fat": False,
        "weight_unit": "lb", **UNSET_OPTIONALS,
    }
    assert client.put("/api/settings", json=updated).json() == updated
    assert client.get("/api/settings").json() == updated


def test_body_profile_round_trips(client):
    profile = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "weight_unit": "kg",
        "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
        "activity_level": "moderate", "goal_rate_kg_per_week": -0.5,
        "targets_auto": False,
        "water_goal_ml": None, "water_quick_adds": None,
        "steps_goal": None,
    }
    assert client.put("/api/settings", json=profile).json() == profile
    assert client.get("/api/settings").json() == profile


def test_a_put_without_profile_fields_leaves_them_alone(client):
    """The stale-bundle guarantee: omitting a field must not blank it.

    This app is an installed PWA, so a tab opened before the deploy that added
    the body profile goes on PUTting a body without those keys until it is
    reloaded. Under the replace semantics the other six fields use, that would
    silently wipe the user's height and birth date on their next save.
    """
    client.put("/api/settings", json={
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "height_cm": 175.0, "sex": "female",
    })

    legacy_body = {
        "calorie_goal": 2300, "protein_goal": 160, "carbs_goal": 260,
        "fat_goal": 75, "track_carbs": False, "track_fat": False,
    }
    saved = client.put("/api/settings", json=legacy_body).json()

    assert saved["height_cm"] == 175.0
    assert saved["sex"] == "female"
    assert saved["calorie_goal"] == 2300  # the replaced fields still replace


def test_an_explicit_null_still_clears_a_profile_field(client):
    """"Did not send" and "sent null" are different, and only one is a no-op."""
    base = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    client.put("/api/settings", json={**base, "height_cm": 175.0})
    saved = client.put("/api/settings", json={**base, "height_cm": None}).json()
    assert saved["height_cm"] is None


def test_settings_reject_implausible_profile_values(client):
    base = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    bad_values = [
        ("height_cm", 0), ("height_cm", -170), ("height_cm", 5000),
        ("sex", "other"), ("sex", "Male"),
        ("activity_level", "athlete"), ("activity_level", ""),
        ("goal_rate_kg_per_week", 50), ("goal_rate_kg_per_week", -50),
        ("birth_date", "2099-01-01"), ("birth_date", "1600-01-01"),
    ]
    for field, bad in bad_values:
        response = client.put("/api/settings", json={**base, field: bad})
        assert response.status_code == 422, f"{field}={bad!r} was accepted"


def test_a_goal_rate_the_clamp_will_reduce_is_still_accepted(client):
    """The clamp explains itself; a 422 does not.

    -3 kg/week is not a typo, it is an over-ambitious plan. It has to reach
    `target_calories` so the response can say why the target it gets back is
    not the one that rate implies.
    """
    base = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
    }
    response = client.put("/api/settings", json={**base, "goal_rate_kg_per_week": -3})
    assert response.status_code == 200
    assert response.json()["goal_rate_kg_per_week"] == -3


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


def test_water_quick_adds_round_trip_as_a_list_not_a_string(client):
    """The column is TEXT and the API field is a list, and this is the seam.

    Without the explicit conversion in routers/settings.py, Pydantic reads the
    raw JSON *string* off the ORM row for a list field and every GET
    /api/settings 500s. That is the third incarnation of a trap this codebase
    has hit -- UserOut.is_admin and MealTemplate.items were the other two --
    and it is the reason the column is named water_quick_adds_json rather than
    matching the field.
    """
    settings = client.get("/api/settings").json()
    # Unset means "use the shipped defaults", which the client resolves.
    assert settings["water_quick_adds"] is None

    saved = client.put(
        "/api/settings", json={**settings, "water_quick_adds": [200.0, 400.0]}
    ).json()
    assert saved["water_quick_adds"] == [200.0, 400.0]

    # The read path is the half that actually breaks, so assert it separately
    # rather than trusting the PUT response.
    reread = client.get("/api/settings").json()
    assert reread["water_quick_adds"] == [200.0, 400.0]
    assert isinstance(reread["water_quick_adds"], list)


def test_water_quick_adds_can_be_cleared_back_to_the_defaults(client):
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "water_quick_adds": [100.0]})
    client.put("/api/settings", json={**settings, "water_quick_adds": None})
    assert client.get("/api/settings").json()["water_quick_adds"] is None


def test_a_put_without_water_fields_leaves_them_alone(client):
    """The stale-bundle guarantee, extended to water.

    A phone running the bundle from before this deploy PUTs a body with no
    water keys. Under the replace semantics the original goals use, that would
    silently wipe a custom goal and any edited quick-add amounts.
    """
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={
        **settings, "water_goal_ml": 3000.0, "water_quick_adds": [300.0],
    })

    legacy_body = {
        "calorie_goal": 2300, "protein_goal": 160, "carbs_goal": 260,
        "fat_goal": 75, "track_carbs": False, "track_fat": False,
    }
    saved = client.put("/api/settings", json=legacy_body).json()

    assert saved["water_goal_ml"] == 3000.0
    assert saved["water_quick_adds"] == [300.0]
    # The replaced fields did move, which is the half that should.
    assert saved["calorie_goal"] == 2300


def test_a_put_without_steps_fields_leaves_them_alone(client):
    """The same guarantee, extended to the step goal.

    A phone still running the pre-deploy bundle PUTs a body with no steps key.
    Under the replace semantics the four goals use, that would silently clear a
    goal the user set -- and because null is a legal state here, nothing about
    the result would look wrong afterwards.
    """
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "steps_goal": 9000})

    legacy_body = {
        "calorie_goal": 2300, "protein_goal": 160, "carbs_goal": 260,
        "fat_goal": 75, "track_carbs": False, "track_fat": False,
    }
    saved = client.put("/api/settings", json=legacy_body).json()

    assert saved["steps_goal"] == 9000
    assert saved["calorie_goal"] == 2300


def test_a_steps_goal_can_be_cleared_on_purpose(client):
    """Clearing is sending null explicitly, which model_fields_set separates
    from not sending the key at all -- the distinction the test above relies on
    in the other direction."""
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "steps_goal": 9000})

    saved = client.put(
        "/api/settings", json={**settings, "steps_goal": None}
    ).json()
    assert saved["steps_goal"] is None


def test_water_settings_bounds_are_refused(client):
    settings = client.get("/api/settings").json()

    # Above the safe-intake ceiling.
    assert client.put(
        "/api/settings", json={**settings, "water_goal_ml": 12000}
    ).status_code == 422
    assert client.put(
        "/api/settings", json={**settings, "water_goal_ml": 0}
    ).status_code == 422
    # A single button larger than a large bottle.
    assert client.put(
        "/api/settings", json={**settings, "water_quick_adds": [2500.0]}
    ).status_code == 422
    # More buttons than fit on a phone.
    assert client.put(
        "/api/settings",
        json={**settings, "water_quick_adds": [100.0, 200.0, 300.0, 400.0, 500.0]},
    ).status_code == 422
    # An empty list is not "use the defaults" -- null is. An empty list would
    # render a card with no way to log anything.
    assert client.put(
        "/api/settings", json={**settings, "water_quick_adds": []}
    ).status_code == 422
