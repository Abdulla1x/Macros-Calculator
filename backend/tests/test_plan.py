from datetime import date, timedelta

from app.banking import MAX_PLAN_DAYS

# A fresh account: 2000 kcal goal, no body profile, so no measured TDEE and the
# floor is the 1200 kcal fallback. That leaves 800 kcal a day of room, which is
# what keeps these tests about the routes rather than about the floor --
# tests/test_banking.py covers the floor itself.
BASE_CALORIES = 2000.0
TODAY = date.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def plan_body(**overrides):
    body = {
        "kind": "planned",
        "event_date": day(2),
        "dates": [day(3), day(4)],
        "calorie_delta": 600,
    }
    body.update(overrides)
    return body


def log(client, when: str, calories: float, name: str = "Dinner"):
    return client.post(
        "/api/meals",
        json={"date": when, "name": name, "calories": calories, "protein": 30},
    )


# --- GET /api/plan/day -------------------------------------------------------


def test_an_unadjusted_day_returns_the_stored_goals_and_a_null_delta(client):
    body = client.get("/api/plan/day", params={"date": day(1)}).json()
    assert body["calorie_goal"] == BASE_CALORIES
    # None rather than 0: an untouched day and a day moved by nothing are
    # different facts, and only one of them has something to cancel.
    assert body["calorie_delta"] is None
    assert body["kind"] is None
    assert body["event_date"] is None


def test_the_day_endpoint_defaults_to_today_and_never_404s(client):
    response = client.get("/api/plan/day")
    assert response.status_code == 200
    assert response.json()["date"] == TODAY.isoformat()


# --- POST /api/plan, planned -------------------------------------------------


def test_a_planned_day_is_funded_by_the_days_named(client):
    created = client.post("/api/plan", json=plan_body()).json()

    assert created["kind"] == "planned"
    assert created["event_date"] == day(2)
    assert [d["date"] for d in created["days"]] == [day(2), day(3), day(4)]
    assert [d["calorie_delta"] for d in created["days"]] == [600, -300, -300]
    # Zero-sum, and reported rather than promised.
    assert created["total_delta"] == 0
    assert created["can_cancel"] is True


def test_the_planned_day_reads_back_raised_and_the_funding_days_shaved(client):
    client.post("/api/plan", json=plan_body())

    assert client.get("/api/plan/day", params={"date": day(2)}).json()[
        "calorie_goal"
    ] == BASE_CALORIES + 600
    for shaved in (day(3), day(4)):
        assert client.get("/api/plan/day", params={"date": shaved}).json()[
            "calorie_goal"
        ] == BASE_CALORIES - 300


def test_protein_holds_while_carbs_and_fat_absorb_the_move(client):
    before = client.get("/api/plan/day", params={"date": day(2)}).json()
    client.post("/api/plan", json=plan_body())
    after = client.get("/api/plan/day", params={"date": day(2)}).json()

    assert after["protein_goal"] == before["protein_goal"]
    assert after["carbs_goal"] > before["carbs_goal"]
    assert after["fat_goal"] > before["fat_goal"]


def test_a_planned_day_can_be_deliberately_smaller(client):
    created = client.post(
        "/api/plan", json=plan_body(calorie_delta=-400)
    ).json()
    assert [d["calorie_delta"] for d in created["days"]] == [-400, 200, 200]
    assert created["total_delta"] == 0


def test_a_planned_request_without_an_amount_is_refused(client):
    response = client.post("/api/plan", json=plan_body(calorie_delta=None))
    assert response.status_code == 422
    assert "how many calories" in response.json()["detail"]


def test_an_uneven_split_still_sums_to_the_whole(client):
    created = client.post(
        "/api/plan",
        json=plan_body(dates=[day(3), day(4), day(5)], calorie_delta=100),
    ).json()
    deltas = [d["calorie_delta"] for d in created["days"]]
    assert deltas == [100, -34, -33, -33]
    assert sum(deltas) == 0


# --- POST /api/plan, compensating -------------------------------------------


def test_the_surplus_is_measured_server_side_not_taken_from_the_client(client):
    log(client, day(-1), 2600)

    created = client.post(
        "/api/plan",
        json={
            "kind": "compensating",
            "event_date": day(-1),
            "dates": [day(1), day(2), day(3)],
            # Sent and ignored: the amount is measured from the meals, so a
            # stale or invented figure cannot become the plan. Inside the
            # per-day bound on purpose -- a value the schema would reject would
            # prove nothing about whether the router consults it.
            "calorie_delta": 2500,
        },
    ).json()

    assert [d["calorie_delta"] for d in created["days"]] == [-200, -200, -200]
    assert created["total_delta"] == -600


def test_compensating_the_other_way_when_a_day_ran_under(client):
    log(client, day(-1), 1400)
    created = client.post(
        "/api/plan",
        json={"kind": "compensating", "event_date": day(-1),
              "dates": [day(1), day(2)]},
    ).json()
    assert [d["calorie_delta"] for d in created["days"]] == [300, 300]


def test_a_day_with_nothing_logged_cannot_be_compensated_for(client):
    response = client.post(
        "/api/plan",
        json={"kind": "compensating", "event_date": day(-1), "dates": [day(1)]},
    )
    # Zero meals is a day nobody recorded, not a day of eating nothing. Without
    # this guard the surplus would read as -2000 and invite a large and
    # entirely fictional compensation.
    assert response.status_code == 422
    assert "nothing to spread" in response.json()["detail"]


def test_a_day_that_landed_on_target_has_nothing_to_spread(client):
    log(client, day(-1), BASE_CALORIES)
    response = client.post(
        "/api/plan",
        json={"kind": "compensating", "event_date": day(-1), "dates": [day(1)]},
    )
    assert response.status_code == 422
    assert "landed on its target" in response.json()["detail"]


def test_the_event_day_cannot_be_one_of_the_days_absorbing_it(client):
    log(client, day(0), 2600)
    response = client.post(
        "/api/plan",
        json={"kind": "compensating", "event_date": day(0),
              "dates": [day(0), day(1)]},
    )
    assert response.status_code == 422
    assert "cannot also be" in response.json()["detail"]


# --- GET /api/plan/surplus ---------------------------------------------------


def test_surplus_reports_consumed_and_reference_separately(client):
    log(client, day(-1), 1500, name="Lunch")
    log(client, day(-1), 1100, name="Dinner")

    body = client.get("/api/plan/surplus", params={"date": day(-1)}).json()
    assert body["consumed_calories"] == 2600
    assert body["reference_calories"] == BASE_CALORIES
    assert body["surplus_calories"] == 600
    assert body["meal_count"] == 2


def test_surplus_is_measured_against_the_target_the_day_actually_had(client):
    # A day that was itself a planned big one is *on plan* when it lands on its
    # raised target. Measuring against the stored goal would report 600 over and
    # invite a compensation for eating exactly what was arranged.
    client.post("/api/plan", json=plan_body(event_date=day(0), dates=[day(1), day(2)]))
    log(client, day(0), 2600)

    body = client.get("/api/plan/surplus", params={"date": day(0)}).json()
    assert body["reference_calories"] == BASE_CALORIES + 600
    assert body["surplus_calories"] == 0
    assert body["calorie_delta"] == 600


def test_a_day_with_no_meals_reports_zero_consumed_and_no_meals(client):
    body = client.get("/api/plan/surplus", params={"date": day(-3)}).json()
    assert body["consumed_calories"] == 0
    assert body["meal_count"] == 0


# --- the past is not adjustable ---------------------------------------------


def test_a_past_day_cannot_be_adjusted(client):
    response = client.post(
        "/api/plan", json=plan_body(event_date=day(-1), dates=[day(1), day(2)])
    )
    assert response.status_code == 422
    assert "already happened" in response.json()["detail"]
    assert day(-1) in response.json()["detail"]


def test_a_past_funding_day_is_refused_too(client):
    response = client.post("/api/plan", json=plan_body(dates=[day(-1), day(3)]))
    assert response.status_code == 422
    assert "already happened" in response.json()["detail"]


# --- overlap -----------------------------------------------------------------


def test_a_second_plan_touching_an_owned_day_is_a_409_naming_the_owner(client):
    client.post("/api/plan", json=plan_body())

    response = client.post(
        "/api/plan",
        json=plan_body(event_date=day(5), dates=[day(4), day(6)]),
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    # Names the day and the plan that owns it, so the fix is actionable rather
    # than a hunt through the planner.
    assert day(4) in detail
    assert day(2) in detail
    # And nothing was written: the refused plan left no partial rows behind.
    assert [p["event_date"] for p in client.get("/api/plan").json()] == [day(2)]


# --- limits ------------------------------------------------------------------


def test_a_plan_wider_than_the_cap_is_refused(client):
    response = client.post(
        "/api/plan",
        json=plan_body(dates=[day(3 + i) for i in range(MAX_PLAN_DAYS + 1)]),
    )
    assert response.status_code == 422


def test_a_plan_reaching_past_the_horizon_is_refused(client):
    response = client.post("/api/plan", json=plan_body(dates=[day(3), day(400)]))
    assert response.status_code == 422


# --- GET /api/plan -----------------------------------------------------------


def test_listing_returns_every_day_of_a_plan(client):
    client.post("/api/plan", json=plan_body())
    plans = client.get("/api/plan").json()
    assert len(plans) == 1
    assert len(plans[0]["days"]) == 3
    assert plans[0]["can_cancel"] is True


def test_listing_is_empty_before_anything_is_planned(client):
    assert client.get("/api/plan").json() == []


# --- DELETE ------------------------------------------------------------------


def test_cancelling_restores_every_upcoming_day(client):
    client.post("/api/plan", json=plan_body())
    assert client.delete(f"/api/plan/{day(2)}").status_code == 204

    for restored in (day(2), day(3), day(4)):
        body = client.get("/api/plan/day", params={"date": restored}).json()
        assert body["calorie_goal"] == BASE_CALORIES
        assert body["calorie_delta"] is None
    assert client.get("/api/plan").json() == []


def test_cancelling_a_plan_that_does_not_exist_is_a_404(client):
    assert client.delete(f"/api/plan/{day(2)}").status_code == 404


def test_cancelling_leaves_days_that_have_already_happened_alone(client):
    # A plan spanning today: today can still be cancelled, and would-be past
    # days cannot be created in the first place, so the boundary this exercises
    # is the one that exists -- today is removable.
    client.post(
        "/api/plan", json=plan_body(event_date=day(0), dates=[day(1)])
    )
    assert client.delete(f"/api/plan/{day(0)}").status_code == 204
    assert client.get("/api/plan/day", params={"date": day(0)}).json()[
        "calorie_delta"
    ] is None


# --- the reason this table exists -------------------------------------------


def test_a_settings_save_rewrites_the_goals_without_erasing_the_plan(client):
    client.post("/api/plan", json=plan_body())

    saved = client.put(
        "/api/settings",
        json={"calorie_goal": 1800, "protein_goal": 150, "carbs_goal": 200,
              "fat_goal": 60, "track_carbs": True, "track_fat": True},
    )
    assert saved.status_code == 200

    # The whole reason adjustments are stored per-day and composed at read time.
    # Written into settings.calorie_goal they would have been overwritten here,
    # with nothing left to say the plan had ever applied.
    assert client.get("/api/plan/day", params={"date": day(2)}).json()[
        "calorie_goal"
    ] == 1800 + 600
    assert client.get("/api/plan/day", params={"date": day(3)}).json()[
        "calorie_goal"
    ] == 1800 - 300


def test_the_plan_router_never_writes_the_four_goal_columns():
    """The invariant, asserted against the source rather than the behaviour.

    Adapted from tests/test_steps.py, and the assertion is deliberately not the
    same one. Steps may not *read* calorie targets; this router legitimately
    does -- reporting a day's target is what it is for. What it must never do is
    persist the answer, because `apply_auto_targets` rewrites all four columns
    on the next weigh-in and the plan would vanish without trace.

    Parsed rather than grepped, which the grep version taught the hard way: the
    module docstring names `apply_auto_targets` in the course of explaining why
    it must never be called, and a text scan cannot tell the prohibition from
    the violation. The AST can -- a keyword argument named `calorie_goal` is not
    an assignment to one, and a name inside a string is not a call.
    """
    import ast
    from pathlib import Path

    import app.routers.plan as plan_module

    goals = {"calorie_goal", "protein_goal", "carbs_goal", "fat_goal"}
    tree = ast.parse(Path(plan_module.__file__).read_text())

    written: list[str] = []
    called: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = getattr(target, "attr", None) or getattr(target, "id", None)
                if name in goals:
                    written.append(f"{name} at line {node.lineno}")
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "apply_auto_targets":
                called.append(f"line {node.lineno}")
            # setattr(row, "calorie_goal", ...) is the same write wearing a hat.
            if name == "setattr" and len(node.args) >= 2:
                second = node.args[1]
                if isinstance(second, ast.Constant) and second.value in goals:
                    written.append(f"setattr at line {node.lineno}")

    assert written == [], f"plan.py writes stored goals: {written}"
    assert called == [], f"plan.py recomputes targets: {called}"
