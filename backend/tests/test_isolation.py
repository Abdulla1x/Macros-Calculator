"""Cross-tenant isolation: two users must never see or modify each other's data."""
from datetime import date, timedelta

from tests.test_meal_ai import configure

MEAL_A = {"date": "2026-07-01", "name": "Alpha Meal", "calories": 500, "protein": 40}
MEAL_B = {"date": "2026-07-01", "name": "Beta Meal", "calories": 300, "protein": 20}
FOOD_A = {"name": "Shared Name Food", "serving_size": 100, "calories": 165, "protein": 31}
TEMPLATE_A = {
    "name": "Shared Name Template", "calories": 620, "protein": 48,
    "items": [{"name": "Alpha Ingredient", "weight_grams": 150,
               "serving_size": 100, "calories": 165, "protein": 31}],
}
# Weigh-in dates are relative: the API rejects future dates.
WEIGH_DAY = (date.today() - timedelta(days=1)).isoformat()
WEIGHT_A = {"date": WEIGH_DAY, "weight_kg": 82.0}
WEIGHT_B = {"date": WEIGH_DAY, "weight_kg": 61.0}

WATER_DAY = date.today().isoformat()
WATER_A = {"date": WATER_DAY, "ml": 250.0}
WATER_B = {"date": WATER_DAY, "ml": 750.0}

STEP_DAY = WATER_DAY
STEPS_A = {"date": STEP_DAY, "steps": 4000}
STEPS_B = {"date": STEP_DAY, "steps": 12000}

DOSE_DAY = WATER_DAY
SUPP_A = {"name": "Alpha Supplement", "dose": "5 g", "times": ["08:00"], "active": True}
SUPP_B = {"name": "Beta Supplement", "dose": "1 cap", "times": ["21:00"], "active": True}

# Plans are the one feature whose dates are deliberately ahead of today, so
# these are relative in the opposite direction from WEIGH_DAY above.
PLAN_EVENT = (date.today() + timedelta(days=3)).isoformat()
PLAN_A = {"kind": "planned", "event_date": PLAN_EVENT,
          "dates": [(date.today() + timedelta(days=4)).isoformat()],
          "calorie_delta": 400}
PLAN_B = {"kind": "planned", "event_date": PLAN_EVENT,
          "dates": [(date.today() + timedelta(days=5)).isoformat()],
          "calorie_delta": 600}


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


def test_cannot_update_another_users_meal(client, client_b):
    a_meal = client.post("/api/meals", json=MEAL_A).json()

    hijack = client_b.put(f"/api/meals/{a_meal['id']}", json=MEAL_B)
    assert hijack.status_code == 404
    # A's meal is untouched.
    assert client.get("/api/meals").json()[0]["name"] == "Alpha Meal"


def test_meal_templates_are_scoped(client, client_b):
    a_template = client.post("/api/meal-templates", json=TEMPLATE_A).json()

    assert client_b.get("/api/meal-templates").json() == []
    assert client_b.delete(f"/api/meal-templates/{a_template['id']}").status_code == 404
    # A's template is untouched, ingredients included.
    a_listed = client.get("/api/meal-templates").json()
    assert [t["id"] for t in a_listed] == [a_template["id"]]
    assert a_listed[0]["items"][0]["name"] == "Alpha Ingredient"


def test_same_template_name_allowed_per_user(client, client_b):
    client.post("/api/meal-templates", json=TEMPLATE_A)
    # The unique index is per user, so B's save is an insert, not an upsert of
    # A's row -- the same property the foods index has.
    b_template = client_b.post(
        "/api/meal-templates",
        json={**TEMPLATE_A, "name": "shared name template", "calories": 999},
    )
    assert b_template.status_code == 201

    assert client.get("/api/meal-templates").json()[0]["calories"] == 620
    assert client_b.get("/api/meal-templates").json()[0]["calories"] == 999


def test_food_library_is_scoped(client, client_b):
    a_food = client.post("/api/foods", json=FOOD_A).json()

    assert client_b.get("/api/foods").json() == []
    assert client_b.get("/api/foods/search", params={"q": "Shared"}).json() == []
    assert client_b.delete(f"/api/foods/{a_food['id']}").status_code == 404
    # The edit verb, probed with values that differ from A's on every field, so
    # a scope failure could not pass as a no-op: if this ever stopped being a
    # 404 the assertions below would show exactly what B managed to rewrite.
    assert (
        client_b.put(
            f"/api/foods/{a_food['id']}",
            json={**FOOD_A, "name": "Renamed By B", "calories": 999},
        ).status_code
        == 404
    )
    assert [f["id"] for f in client.get("/api/foods").json()] == [a_food["id"]]
    assert client.get("/api/foods").json()[0]["name"] == FOOD_A["name"]
    assert client.get("/api/foods").json()[0]["calories"] == FOOD_A["calories"]


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


def test_weight_lists_are_scoped(client, client_b):
    a_weight = client.post("/api/weights", json=WEIGHT_A).json()
    client_b.post("/api/weights", json=WEIGHT_B)

    a_weights = client.get("/api/weights").json()
    b_weights = client_b.get("/api/weights").json()
    assert [w["weight_kg"] for w in a_weights] == [82.0]
    assert [w["weight_kg"] for w in b_weights] == [61.0]
    assert all(w["id"] != a_weight["id"] for w in b_weights)

    # The date-filtered listing is scoped too.
    b_ranged = client_b.get(
        "/api/weights", params={"start": WEIGH_DAY, "end": WEIGH_DAY}
    ).json()
    assert [w["weight_kg"] for w in b_ranged] == [61.0]


def test_cannot_delete_another_users_weight(client, client_b):
    a_weight = client.post("/api/weights", json=WEIGHT_A).json()

    assert client_b.delete(f"/api/weights/{a_weight['id']}").status_code == 404
    # A's weigh-in is untouched.
    assert [w["id"] for w in client.get("/api/weights").json()] == [a_weight["id"]]


def test_weight_upsert_does_not_overwrite_another_users_day(client, client_b):
    """Same date, two accounts: B's upsert must insert, not update A's row."""
    a_weight = client.post("/api/weights", json=WEIGHT_A).json()
    b_weight = client_b.post("/api/weights", json=WEIGHT_B).json()

    assert a_weight["id"] != b_weight["id"]
    assert client.get("/api/weights").json()[0]["weight_kg"] == 82.0
    assert client_b.get("/api/weights").json()[0]["weight_kg"] == 61.0


def test_weight_trend_only_counts_own_entries(client, client_b):
    client.post("/api/weights", json=WEIGHT_A)
    client_b.post("/api/weights", json=WEIGHT_B)

    assert client.get("/api/weights/trend").json()["latest_trend_kg"] == 82.0
    assert client_b.get("/api/weights/trend").json()["latest_trend_kg"] == 61.0


def test_full_export_only_contains_own_weights(client, client_b):
    client.post("/api/weights", json=WEIGHT_A)
    client_b.post("/api/weights", json=WEIGHT_B)

    b_export = client_b.get("/api/data/export/all").json()
    assert [w["weight_kg"] for w in b_export["weights"]] == [61.0]


def test_water_days_are_scoped(client, client_b):
    a_entry = client.post("/api/water", json=WATER_A).json()
    client_b.post("/api/water", json=WATER_B)

    a_day = client.get("/api/water", params={"date": WATER_DAY}).json()
    b_day = client_b.get("/api/water", params={"date": WATER_DAY}).json()
    # Same calendar day, two accounts: neither total may include the other.
    assert a_day["total_ml"] == 250.0
    assert b_day["total_ml"] == 750.0
    assert all(e["id"] != a_entry["id"] for e in b_day["entries"])


def test_cannot_delete_another_users_water_entry(client, client_b):
    a_entry = client.post("/api/water", json=WATER_A).json()

    assert client_b.delete(f"/api/water/{a_entry['id']}").status_code == 404
    # A's entry is untouched.
    assert client.get("/api/water").json()["total_ml"] == 250.0


def test_a_water_goal_never_reads_another_users_weight(client, client_b):
    """The derived goal reaches outside the water table, which is what makes it
    worth a test here rather than only in test_water.py: it queries `weights`,
    and a missing user_id filter there would hand B a goal computed from A's
    body."""
    client.post("/api/weights", json=WEIGHT_A)   # A weighs 82 kg
    client_b.post("/api/weights", json=WEIGHT_B)  # B weighs 61 kg

    a_goal = client.get("/api/water").json()
    b_goal = client_b.get("/api/water").json()
    assert a_goal["goal_basis"]["weight_kg"] == 82.0
    assert b_goal["goal_basis"]["weight_kg"] == 61.0
    assert a_goal["goal_ml"] != b_goal["goal_ml"]


def test_full_export_only_contains_own_water(client, client_b):
    client.post("/api/water", json=WATER_A)
    client_b.post("/api/water", json=WATER_B)

    b_export = client_b.get("/api/data/export/all").json()
    assert [w["ml"] for w in b_export["water_logs"]] == [750.0]


def test_step_days_are_scoped(client, client_b):
    client.post("/api/steps", json=STEPS_A)
    client_b.post("/api/steps", json=STEPS_B)

    # Same calendar day, two accounts. Unlike water there is no summing here --
    # the risk is the unique index being enforced across users rather than
    # within one, so B's write would overwrite A's day instead of adding a row.
    assert client.get("/api/steps", params={"date": STEP_DAY}).json()["steps"] == 4000
    assert client_b.get("/api/steps", params={"date": STEP_DAY}).json()["steps"] == 12000


def test_cannot_clear_another_users_steps(client, client_b):
    client.post("/api/steps", json=STEPS_A)

    assert client_b.delete("/api/steps", params={"date": STEP_DAY}).status_code == 404
    # A's day is untouched, and still logged rather than merely reading zero.
    a_day = client.get("/api/steps", params={"date": STEP_DAY}).json()
    assert a_day["steps"] == 4000
    assert a_day["logged"] is True


def test_a_steps_burn_never_reads_another_users_weight(client, client_b):
    """The walking estimate reaches outside the steps table, exactly the way the
    water goal reaches outside its own -- it queries `weights`, and a missing
    user_id filter there would hand B a figure computed from A's body."""
    client.post("/api/weights", json=WEIGHT_A)   # A weighs 82 kg
    client_b.post("/api/weights", json=WEIGHT_B)  # B weighs 61 kg
    client.post("/api/steps", json=STEPS_A)
    client_b.post("/api/steps", json={**STEPS_B, "steps": 4000})

    a_day = client.get("/api/steps", params={"date": STEP_DAY}).json()
    b_day = client_b.get("/api/steps", params={"date": STEP_DAY}).json()
    assert a_day["burn_weight_kg"] == 82.0
    assert b_day["burn_weight_kg"] == 61.0
    # Same step count, different bodies, so the same filter failure would show
    # up as identical burns.
    assert a_day["burn_kcal"] != b_day["burn_kcal"]


def test_full_export_only_contains_own_steps(client, client_b):
    client.post("/api/steps", json=STEPS_A)
    client_b.post("/api/steps", json=STEPS_B)

    b_export = client_b.get("/api/data/export/all").json()
    assert [s["steps"] for s in b_export["steps"]] == [12000]


def test_supplement_lists_are_scoped(client, client_b):
    client.post("/api/supplements", json=SUPP_A)
    client_b.post("/api/supplements", json=SUPP_B)

    assert [s["name"] for s in client.get("/api/supplements").json()] == [
        "Alpha Supplement"
    ]
    assert [s["name"] for s in client_b.get("/api/supplements").json()] == [
        "Beta Supplement"
    ]


def test_the_same_supplement_name_is_allowed_per_user(client, client_b):
    """The uniqueness index spans (user_id, lower(name)), not lower(name).

    Half the world takes creatine; a name one account has claimed must not be
    unavailable to everyone else.
    """
    assert client.post("/api/supplements", json=SUPP_A).status_code == 201
    assert client_b.post("/api/supplements", json=SUPP_A).status_code == 201


def test_a_dose_check_off_is_double_scoped(client, client_b):
    """The supplement_id on a log write is an id the *client* chose.

    Same shape as the analysis-to-meal link above, and the same danger: without
    the ownership check it would write a row into someone else's history, or
    reveal by its status code that a guessed id exists.
    """
    a_supp = client.post("/api/supplements", json=SUPP_A).json()

    assert client_b.post(
        "/api/supplements/log",
        json={"supplement_id": a_supp["id"], "date": DOSE_DAY, "time": "08:00"},
    ).status_code == 404

    assert client_b.delete(
        "/api/supplements/log",
        params={"supplement_id": a_supp["id"], "date": DOSE_DAY, "time": "08:00"},
    ).status_code == 404

    # A's own day is untouched by both attempts.
    assert client.get("/api/supplements/day", params={"date": DOSE_DAY}).json()[
        "taken"
    ] == 0


def test_cannot_edit_or_delete_another_users_supplement(client, client_b):
    a_supp = client.post("/api/supplements", json=SUPP_A).json()

    assert client_b.put(
        f"/api/supplements/{a_supp['id']}",
        json={"name": "Hijacked", "dose": None, "times": ["08:00"], "active": False},
    ).status_code == 404
    assert client_b.delete(f"/api/supplements/{a_supp['id']}").status_code == 404

    still = client.get("/api/supplements").json()
    assert still[0]["name"] == "Alpha Supplement"
    assert still[0]["active"] is True


def test_supplement_days_are_scoped(client, client_b):
    a_supp = client.post("/api/supplements", json=SUPP_A).json()
    b_supp = client_b.post("/api/supplements", json=SUPP_B).json()
    client.post(
        "/api/supplements/log",
        json={"supplement_id": a_supp["id"], "date": DOSE_DAY, "time": "08:00"},
    )

    a_day = client.get("/api/supplements/day", params={"date": DOSE_DAY}).json()
    b_day = client_b.get("/api/supplements/day", params={"date": DOSE_DAY}).json()

    assert [s["name"] for s in a_day["slots"]] == ["Alpha Supplement"]
    assert a_day["taken"] == 1
    assert [s["name"] for s in b_day["slots"]] == ["Beta Supplement"]
    assert b_day["taken"] == 0
    assert b_supp["id"] != a_supp["id"]


def test_full_export_only_contains_own_supplements(client, client_b):
    a_supp = client.post("/api/supplements", json=SUPP_A).json()
    client_b.post("/api/supplements", json=SUPP_B)
    client.post(
        "/api/supplements/log",
        json={"supplement_id": a_supp["id"], "date": DOSE_DAY, "time": "08:00"},
    )

    b_export = client_b.get("/api/data/export/all").json()
    assert [s["name"] for s in b_export["supplements"]] == ["Beta Supplement"]
    assert b_export["supplement_logs"] == []


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


def test_admin_privilege_does_not_leak_to_other_users(client, client_b, monkeypatch):
    """The admin routes are the one place in this app that reads across tenants,
    so the tier that opens them belongs in the isolation gate too.

    B stays a normal user while A is an admin, and B's data stays B's: being
    on the allowlist grants aggregate metrics, never another account's rows.
    """
    monkeypatch.setenv("ADMIN_EMAILS", client.get("/api/auth/me").json()["email"])
    b_meal = client_b.post("/api/meals", json=MEAL_B).json()

    assert client.get("/api/admin/stats").status_code == 200
    assert client_b.get("/api/admin/stats").status_code == 403
    assert client_b.get("/api/admin/users").status_code == 403

    # Admin is not a master key: the ordinary scoped routes ignore it entirely.
    assert client.put(f"/api/meals/{b_meal['id']}", json=MEAL_A).status_code == 404
    assert client.delete(f"/api/meals/{b_meal['id']}").status_code == 404
    assert [m["name"] for m in client.get("/api/meals").json()] == []
    assert client.get("/api/data/export/all").json()["meals"] == []


def test_targets_never_read_another_users_weigh_ins(client, client_b):
    """The calorie target is the app's first cross-table read.

    `compute_targets` reaches out of the settings row into `weights` to find
    the user's current weight, which is a new shape of query for this suite:
    every other endpoint answers from one table it already filtered. A missing
    user_id filter there would not leak a weight directly — it would quietly
    compute one tenant's calorie target from another tenant's body.
    """
    profile = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
        "activity_level": "moderate", "goal_rate_kg_per_week": 0.0,
    }
    client.put("/api/settings", json=profile)
    client_b.put("/api/settings", json=profile)

    # Only B has weighed in. A's profile is otherwise identical, so if the
    # query were unscoped A would silently get B's target instead of none.
    client_b.post("/api/weights", json=WEIGHT_B)

    a_targets = client.get("/api/settings/targets").json()
    assert "weight" in a_targets["missing"]
    assert a_targets["target_calories"] is None
    assert a_targets["weight_kg"] is None

    b_targets = client_b.get("/api/settings/targets").json()
    assert b_targets["weight_kg"] == WEIGHT_B["weight_kg"]
    assert b_targets["target_calories"] is not None


def test_a_measured_tdee_never_eats_another_users_meals(client, client_b):
    """Targets now read a *second* user-owned table, so the gate needs widening.

    Measured TDEE averages the account's logged intake. An unscoped meals query
    would not leak a meal name anywhere visible — it would fold a stranger's
    eating into this user's measured burn and then into the goals written on
    their dashboard, which is a leak that shows up only as a wrong number.

    B logs a dense, measurable history. A logs an identical weigh-in history
    with no meals at all, so if the intake query were unscoped A would measure
    B's diet.
    """
    profile = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
        "activity_level": "moderate", "goal_rate_kg_per_week": 0.0,
    }
    client.put("/api/settings", json=profile)
    client_b.put("/api/settings", json=profile)

    for days_ago in range(1, 21):
        day = (date.today() - timedelta(days=days_ago)).isoformat()
        for who in (client, client_b):
            who.post("/api/weights", json={"date": day, "weight_kg": 80.0})
        client_b.post(
            "/api/meals",
            json={"date": day, "name": "Beta Meal", "calories": 3300, "protein": 100},
        )

    a_targets = client.get("/api/settings/targets").json()
    b_targets = client_b.get("/api/settings/targets").json()

    # B has the logs, so B gets measured.
    assert b_targets["tdee_source"] == "measured"
    assert b_targets["tdee_basis"]["logged_days"] == 20

    # A has none, so A must fall back rather than inherit B's intake.
    assert a_targets["tdee_source"] == "estimated"
    assert a_targets["tdee_basis"]["logged_days"] == 0
    assert a_targets["tdee"] != b_targets["tdee"]


def test_auto_targets_are_computed_from_your_own_body(client, client_b):
    """Same query, but on the write path: a weigh-in rewrites goals, and it
    must rewrite only the goals of the account that logged it."""
    profile = {
        "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
        "fat_goal": 70, "track_carbs": False, "track_fat": False,
        "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
        "activity_level": "moderate", "goal_rate_kg_per_week": 0.0,
        "targets_auto": True,
    }
    client.put("/api/settings", json=profile)
    client_b.put("/api/settings", json=profile)

    client.post("/api/weights", json=WEIGHT_A)
    client_b.post("/api/weights", json=WEIGHT_B)

    a_goal = client.get("/api/settings").json()["calorie_goal"]
    b_goal = client_b.get("/api/settings").json()["calorie_goal"]
    # 82 kg and 61 kg cannot produce the same maintenance target.
    assert a_goal != b_goal


def test_plan_lists_are_scoped(client, client_b):
    assert client.post("/api/plan", json=PLAN_A).status_code == 201
    # The same event day, which the unique index allows across accounts and
    # must: two people may both be going out on the 28th.
    assert client_b.post("/api/plan", json=PLAN_B).status_code == 201

    a_deltas = [d["calorie_delta"] for d in client.get("/api/plan").json()[0]["days"]]
    b_deltas = [d["calorie_delta"] for d in client_b.get("/api/plan").json()[0]["days"]]
    assert sorted(a_deltas) == [-400, 400]
    assert sorted(b_deltas) == [-600, 600]


def test_a_planned_day_never_moves_another_users_target(client, client_b):
    """The read path that composes an adjustment onto the stored goals.

    Every ring on the dashboard is drawn from this endpoint, so a scoping miss
    here would not show up as someone else's data on screen -- it would show up
    as your own calorie target quietly being wrong.
    """
    client.post("/api/plan", json=PLAN_A)

    a_day = client.get("/api/plan/day", params={"date": PLAN_EVENT}).json()
    b_day = client_b.get("/api/plan/day", params={"date": PLAN_EVENT}).json()
    assert a_day["calorie_delta"] == 400
    assert b_day["calorie_delta"] is None
    assert b_day["calorie_goal"] == 2000


def test_a_surplus_is_measured_from_your_own_meals(client, client_b):
    """The surplus reaches outside the plan table into meals, exactly the way
    the steps burn reaches into weights -- and the same scoping question."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post("/api/meals", json={**MEAL_A, "date": yesterday, "calories": 2600})

    a = client.get("/api/plan/surplus", params={"date": yesterday}).json()
    b = client_b.get("/api/plan/surplus", params={"date": yesterday}).json()
    assert a["consumed_calories"] == 2600
    assert b["consumed_calories"] == 0
    assert b["meal_count"] == 0


def test_cannot_cancel_another_users_plan(client, client_b):
    client.post("/api/plan", json=PLAN_A)

    assert client_b.delete(f"/api/plan/{PLAN_EVENT}").status_code == 404
    # And A still has it, whole.
    assert len(client.get("/api/plan").json()[0]["days"]) == 2


def test_one_users_plan_does_not_block_anothers_day(client, client_b):
    """The unique index spans (user_id, date), not date.

    Overlap is refused *within* an account, and the 409 that enforces it must
    not leak across one -- being told your Saturday is taken because a stranger
    banked theirs would be both wrong and disclosive.
    """
    client.post("/api/plan", json=PLAN_A)
    assert client_b.post("/api/plan", json=PLAN_A).status_code == 201


def test_full_export_only_contains_own_plans(client, client_b):
    client.post("/api/plan", json=PLAN_A)
    client_b.post("/api/plan", json=PLAN_B)

    b_export = client_b.get("/api/data/export/all").json()
    assert sorted(r["calorie_delta"] for r in b_export["calorie_plans"]) == [-600, 600]


def test_calibration_never_measures_another_users_corrections(client, client_b, monkeypatch):
    """Calibration reads a *second* user-owned table, so the gate needs widening.

    An unscoped join would not leak a meal name anywhere visible. It would fold
    a stranger's corrections into this account's coverage rate and print the
    result as a statement about their own estimates -- a leak that shows up only
    as a wrong number, which is the kind this suite exists to catch.

    B corrects a dense history. A runs the same analyses and saves none of them,
    so if the join were unscoped A would inherit B's entire correction record.
    """
    from app.calibration import CALIBRATION_MIN_SAMPLES
    from tests.test_meal_ai import SAMPLE

    configure(monkeypatch)
    today = date.today().isoformat()

    for index in range(CALIBRATION_MIN_SAMPLES):
        # B saves a corrected value, well outside the estimate.
        analysis = client_b.post("/api/ai/analyze", data={"text": "dinner"}).json()
        meal = client_b.post(
            "/api/meals",
            json={
                "date": today,
                "name": f"Beta Meal {index}",
                "calories": SAMPLE.calories.estimate + 100,
                "protein": SAMPLE.protein.estimate + 10,
            },
        ).json()
        client_b.patch(
            f"/api/ai/analyses/{analysis['analysis_id']}", json={"meal_id": meal["id"]}
        )
        # A runs the analysis but never saves a meal from it.
        client.post("/api/ai/analyze", data={"text": "dinner"})

    a_calibration = client.get("/api/ai/calibration").json()
    b_calibration = client_b.get("/api/ai/calibration").json()

    # B did the work, so B gets the measurement.
    assert b_calibration["linked"] == CALIBRATION_MIN_SAMPLES
    assert b_calibration["calories"]["corrected"] == CALIBRATION_MIN_SAMPLES
    assert b_calibration["calories"]["coverage_pct"] is not None

    # A logged the same number of analyses and linked none of them, so A must
    # measure nothing rather than inherit B's record.
    assert a_calibration["analyses"] == CALIBRATION_MIN_SAMPLES
    assert a_calibration["linked"] == 0
    assert a_calibration["corrected"] == 0
    assert a_calibration["calories"]["coverage_pct"] is None
    assert a_calibration["unavailable_reason"] is not None
