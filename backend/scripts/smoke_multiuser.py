"""Live two-account isolation smoke test.

Runs against a real, running deployment (local or production) and proves via
direct API calls that two accounts cannot see or modify each other's data.

Usage:
    BASE_URL=http://localhost:8000 python scripts/smoke_multiuser.py
    BASE_URL=https://<service>.onrender.com python scripts/smoke_multiuser.py

If DATABASE_URL is also set, the script additionally connects to the database
and asserts row-level ownership directly.

Leaves behind the two throwaway accounts; their data is removed via the API
where possible. (DELETE /api/auth/account exists and would clean them up
properly — worth wiring in, but it needs the password kept to hand.)
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
PASSWORD = "smoke-test-password-1"

_checks = 0


def check(condition: bool, label: str) -> None:
    global _checks
    _checks += 1
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        sys.exit(f"FAILED: {label}")


def make_user(client: httpx.Client, tag: str) -> tuple[dict[str, str], dict]:
    email = f"smoke-{tag}-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/signup", json={"email": email, "password": PASSWORD}
    )
    check(response.status_code == 201, f"signup {tag} ({email})")
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


def main() -> None:
    print(f"Target: {BASE_URL}")
    with httpx.Client(base_url=BASE_URL, timeout=60) as client:
        check(client.get("/api/health").status_code == 200, "health check")

        # -- Anonymous access is rejected everywhere --------------------------
        for method, path in [
            ("GET", "/api/meals"),
            ("GET", "/api/foods"),
            ("GET", "/api/meal-templates"),
            ("GET", "/api/settings"),
            ("GET", "/api/analytics/daily"),
            ("GET", "/api/data/export"),
            ("GET", "/api/plan"),
            ("GET", "/api/plan/day"),
            ("GET", "/api/plan/surplus"),
            ("POST", "/api/ai/analyze"),
            ("GET", "/api/ai/calibration"),
        ]:
            response = client.request(method, path)
            check(response.status_code == 401, f"anon {method} {path} -> 401")

        # -- Two accounts, disjoint data --------------------------------------
        headers_a, user_a = make_user(client, "a")
        headers_b, user_b = make_user(client, "b")
        check(user_a["id"] != user_b["id"], "distinct user ids")

        me_a = client.get("/api/auth/me", headers=headers_a).json()
        me_b = client.get("/api/auth/me", headers=headers_b).json()
        check(me_a == user_a and me_b == user_b, "tokens map to correct identities")

        a_meal_ids = []
        for meal in (
            {"date": "2026-07-01", "name": "Smoke Alpha One", "calories": 500, "protein": 40},
            {"date": "2026-07-02", "name": "Smoke Alpha Two", "calories": 350, "protein": 25},
        ):
            response = client.post("/api/meals", json=meal, headers=headers_a)
            check(response.status_code == 201, f"A creates meal {meal['name']}")
            a_meal_ids.append(response.json()["id"])

        response = client.post(
            "/api/meals",
            json={"date": "2026-07-01", "name": "Smoke Beta One", "calories": 300, "protein": 20},
            headers=headers_b,
        )
        check(response.status_code == 201, "B creates meal")
        b_meal_id = response.json()["id"]

        food = {"name": "Smoke Shared Food", "serving_size": 100, "calories": 100, "protein": 10}
        a_food_id = client.post("/api/foods", json=food, headers=headers_a).json()["id"]
        b_food = client.post(
            "/api/foods", json={**food, "calories": 999}, headers=headers_b
        )
        check(b_food.status_code == 201, "B can own a food with A's food name")
        b_food_id = b_food.json()["id"]
        check(a_food_id != b_food_id, "same-named foods are distinct rows")

        # Same template name for both accounts: the unique index is keyed on
        # (user_id, lower(name)), so B's save must insert rather than update A's.
        template = {
            "name": "Smoke Shared Template", "calories": 620, "protein": 48,
            "items": [{"name": "Smoke Alpha Ingredient", "weight_grams": 150,
                       "serving_size": 100, "calories": 165, "protein": 31}],
        }
        response = client.post("/api/meal-templates", json=template, headers=headers_a)
        check(response.status_code == 201, "A creates a meal template")
        a_template_id = response.json()["id"]
        check(response.json()["created"] is True, "A's template reports created=true")
        b_template = client.post(
            "/api/meal-templates",
            json={**template, "calories": 999, "items": []},
            headers=headers_b,
        )
        check(b_template.status_code == 201, "B can own a template with A's name")
        b_template_id = b_template.json()["id"]
        check(a_template_id != b_template_id, "same-named templates are distinct rows")

        # Same weigh-in date for both accounts: the upsert is keyed on
        # (user_id, date), so B's write must insert rather than update A's row.
        weigh_day = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        response = client.post(
            "/api/weights",
            json={"date": weigh_day, "weight_kg": 82.5},
            headers=headers_a,
        )
        check(response.status_code == 200, "A logs a weigh-in")
        a_weight_id = response.json()["id"]
        response = client.post(
            "/api/weights",
            json={"date": weigh_day, "weight_kg": 61.0},
            headers=headers_b,
        )
        check(response.status_code == 200, "B logs a weigh-in on the same date")
        b_weight_id = response.json()["id"]
        check(a_weight_id != b_weight_id, "same-date weigh-ins are distinct rows")

        # Same calendar day for both accounts. Unlike weigh-ins there is no
        # upsert here at all -- every POST inserts -- so this is checking the
        # user_id filter on the read path rather than on a conflict key.
        water_day = datetime.now(timezone.utc).date().isoformat()
        response = client.post(
            "/api/water",
            json={"date": water_day, "ml": 250.0},
            headers=headers_a,
        )
        check(response.status_code == 201, "A logs water")
        a_water_id = response.json()["id"]
        response = client.post(
            "/api/water",
            json={"date": water_day, "ml": 750.0},
            headers=headers_b,
        )
        check(response.status_code == 201, "B logs water on the same date")
        b_water_id = response.json()["id"]
        check(a_water_id != b_water_id, "same-date water logs are distinct rows")

        # Steps upsert on (user_id, date), so the shared date is checking that
        # the unique index is scoped per user: if it were not, B's write would
        # overwrite A's day rather than creating a second row.
        step_day = water_day
        response = client.post(
            "/api/steps",
            json={"date": step_day, "steps": 4000},
            headers=headers_a,
        )
        check(response.status_code == 200, "A logs steps")
        response = client.post(
            "/api/steps",
            json={"date": step_day, "steps": 12000},
            headers=headers_b,
        )
        check(response.status_code == 200, "B logs steps on the same date")
        response = client.post(
            "/api/steps",
            json={"date": step_day, "steps": 12500},
            headers=headers_b,
        )
        check(response.status_code == 200, "B re-logs the same date")

        # Supplements: the same name for both users, which is what proves the
        # uniqueness index is scoped per account rather than globally. Then a
        # dose ticked on a shared date, and a cross-tenant tick that must 404 --
        # supplement_id arrives from the client, so it is the same class of
        # link as ai_analyses.meal_id.
        dose_day = water_day
        response = client.post(
            "/api/supplements",
            json={"name": "Smoke Creatine", "dose": "5 g",
                  "times": ["08:00"], "active": True},
            headers=headers_a,
        )
        check(response.status_code == 201, "A adds a supplement")
        a_supplement_id = response.json()["id"]
        response = client.post(
            "/api/supplements",
            json={"name": "Smoke Creatine", "dose": "3 g",
                  "times": ["21:00"], "active": True},
            headers=headers_b,
        )
        check(response.status_code == 201, "B adds one with the same name")
        b_supplement_id = response.json()["id"]
        check(a_supplement_id != b_supplement_id, "same-name supplements are distinct rows")

        response = client.post(
            "/api/supplements/log",
            json={"supplement_id": a_supplement_id, "date": dose_day, "time": "08:00"},
            headers=headers_a,
        )
        check(response.status_code == 200, "A ticks a dose")
        check(response.json()["taken"] == 1, "A's day reports one dose taken")
        response = client.post(
            "/api/supplements/log",
            json={"supplement_id": a_supplement_id, "date": dose_day, "time": "08:00"},
            headers=headers_a,
        )
        check(
            response.status_code == 200 and response.json()["taken"] == 1,
            "ticking the same dose twice stays one dose",
        )

        # -- Calorie plans: the same event day, claimed by both ---------------
        # The unique index spans (user_id, date), not date, so two accounts
        # banking the same Saturday must both succeed. Getting that wrong would
        # tell B their day is taken because a stranger claimed it -- wrong, and
        # disclosive about someone else's calendar.
        plan_event = (
            datetime.now(timezone.utc).date() + timedelta(days=3)
        ).isoformat()
        plan_fund = (
            datetime.now(timezone.utc).date() + timedelta(days=4)
        ).isoformat()
        plan_body = {"kind": "planned", "event_date": plan_event,
                     "dates": [plan_fund], "calorie_delta": 400}
        response = client.post("/api/plan", json=plan_body, headers=headers_a)
        check(response.status_code == 201, "A banks a day")
        response = client.post(
            "/api/plan", json={**plan_body, "calorie_delta": 600}, headers=headers_b
        )
        check(response.status_code == 201, "B banks the same date independently")
        response = client.post("/api/plan", json=plan_body, headers=headers_a)
        check(
            response.status_code == 409,
            "A banking an already-claimed day of their own -> 409",
        )

        client.put(
            "/api/settings",
            json={"calorie_goal": 1750, "protein_goal": 155, "carbs_goal": 200,
                  "fat_goal": 55, "track_carbs": True, "track_fat": False,
                  "weight_unit": "lb"},
            headers=headers_a,
        )

        # -- Body profile and derived targets ---------------------------------
        # Identical profiles for both users, so the only thing that can make
        # their targets differ is the weigh-in each of them logged. If the
        # weight query inside compute_targets were unscoped, these would match.
        profile = {"height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
                   "activity_level": "moderate", "goal_rate_kg_per_week": 0.0}
        client.put(
            "/api/settings",
            json={"calorie_goal": 1750, "protein_goal": 155, "carbs_goal": 200,
                  "fat_goal": 55, "track_carbs": True, "track_fat": False,
                  "weight_unit": "lb", **profile, "targets_auto": True},
            headers=headers_a,
        )
        client.put(
            "/api/settings",
            json={"calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
                  "fat_goal": 70, "track_carbs": False, "track_fat": False,
                  **profile, "targets_auto": True},
            headers=headers_b,
        )

        a_targets = client.get("/api/settings/targets", headers=headers_a).json()
        b_targets = client.get("/api/settings/targets", headers=headers_b).json()
        check(a_targets["missing"] == [], "A's profile is complete enough to target")
        check(a_targets["weight_kg"] == 82.5, "A's target uses A's weigh-in")
        check(b_targets["weight_kg"] == 61.0, "B's target uses B's weigh-in")
        check(
            a_targets["target_calories"] > b_targets["target_calories"],
            "82.5 kg and 61.0 kg do not produce the same target",
        )

        a_auto = client.get("/api/settings", headers=headers_a).json()
        check(
            a_auto["calorie_goal"] == a_targets["target_calories"],
            "targets_auto wrote A's calorie goal",
        )
        check(
            client.get("/api/settings", headers=headers_b).json()["calorie_goal"]
            == b_targets["target_calories"],
            "targets_auto wrote B's calorie goal from B's own body",
        )

        # A PUT that omits the profile keys must not blank them -- the stale
        # PWA bundle case. Asserted here as well as in pytest because this runs
        # against the real server, where the schema default is what applies.
        client.put(
            "/api/settings",
            json={"calorie_goal": 1750, "protein_goal": 155, "carbs_goal": 200,
                  "fat_goal": 55, "track_carbs": True, "track_fat": False},
            headers=headers_a,
        )
        check(
            client.get("/api/settings", headers=headers_a).json()["height_cm"] == 180.0,
            "a PUT without profile keys leaves the profile alone",
        )

        # -- Read isolation ----------------------------------------------------
        a_names = {m["name"] for m in client.get("/api/meals", headers=headers_a).json()}
        b_names = {m["name"] for m in client.get("/api/meals", headers=headers_b).json()}
        check(a_names == {"Smoke Alpha One", "Smoke Alpha Two"}, "A sees only A's meals")
        check(b_names == {"Smoke Beta One"}, "B sees only B's meals")

        b_foods = client.get("/api/foods", headers=headers_b).json()
        check([f["id"] for f in b_foods] == [b_food_id], "B sees only B's foods")
        check(b_foods[0]["calories"] == 999, "B's upsert did not touch A's food")

        b_templates = client.get("/api/meal-templates", headers=headers_b).json()
        check(
            [t["id"] for t in b_templates] == [b_template_id],
            "B sees only B's meal templates",
        )
        check(b_templates[0]["calories"] == 999, "B's save did not touch A's template")
        a_templates = client.get("/api/meal-templates", headers=headers_a).json()
        check(
            a_templates[0]["items"][0]["name"] == "Smoke Alpha Ingredient",
            "A's template kept its ingredient rows",
        )
        check(b_templates[0]["items"] == [], "B's template has no ingredient rows")

        b_settings = client.get("/api/settings", headers=headers_b).json()
        # B's calorie goal is now derived rather than the 2000 default, so the
        # check that A cannot reach it is made against B's own derived value.
        check(
            b_settings["calorie_goal"] == b_targets["target_calories"],
            "A's settings change invisible to B",
        )
        check(b_settings["weight_unit"] == "kg", "A's unit change invisible to B")

        b_weights = client.get("/api/weights", headers=headers_b).json()
        check(
            [w["weight_kg"] for w in b_weights] == [61.0],
            "B sees only B's weigh-in on the shared date",
        )
        b_trend = client.get("/api/weights/trend", headers=headers_b).json()
        check(b_trend["latest_trend_kg"] == 61.0, "B's trend counts only B")

        b_water = client.get(
            "/api/water", params={"date": water_day}, headers=headers_b
        ).json()
        check(b_water["total_ml"] == 750.0, "B's water total counts only B")
        check(
            b_water["goal_basis"]["weight_kg"] == 61.0,
            "B's water goal derives from B's own weight",
        )

        b_steps = client.get(
            "/api/steps", params={"date": step_day}, headers=headers_b
        ).json()
        check(b_steps["steps"] == 12500, "B's step count is B's latest, not A's")
        check(
            b_steps["burn_weight_kg"] == 61.0,
            "B's walking estimate uses B's own weight",
        )
        a_steps = client.get(
            "/api/steps", params={"date": step_day}, headers=headers_a
        ).json()
        check(a_steps["steps"] == 4000, "A's day survived B writing the same date")

        b_doses = client.get(
            "/api/supplements/day", params={"date": dose_day}, headers=headers_b
        ).json()
        check(
            [slot["dose"] for slot in b_doses["slots"]] == ["3 g"],
            "B's supplement day shows B's own dose, not A's",
        )
        check(b_doses["taken"] == 0, "B has ticked nothing despite A's dose")
        a_doses = client.get(
            "/api/supplements/day", params={"date": dose_day}, headers=headers_a
        ).json()
        check(a_doses["taken"] == 1, "A's dose survived B's identical supplement")

        a_plan_day = client.get(
            "/api/plan/day", params={"date": plan_event}, headers=headers_a
        ).json()
        b_plan_day = client.get(
            "/api/plan/day", params={"date": plan_event}, headers=headers_b
        ).json()
        # Every dashboard ring is drawn from this endpoint, so a scoping miss
        # here shows up as your own calorie target being wrong rather than as
        # someone else's data on screen.
        check(a_plan_day["calorie_delta"] == 400, "A's banked day is A's own amount")
        check(b_plan_day["calorie_delta"] == 600, "B's banked day is B's own amount")
        check(
            a_plan_day["calorie_goal"] != b_plan_day["calorie_goal"],
            "the same date resolves to a different target per account",
        )

        b_analytics = client.get("/api/analytics/daily", headers=headers_b).json()
        check(b_analytics["totals"]["calories"] == 300, "B's analytics count only B")

        # Calibration is an aggregate over a *second* table (the meals each
        # analysis was saved into). An unscoped join would not show a stranger's
        # meal name anywhere -- it would fold their corrections into this
        # account's accuracy figure, which is a leak that only ever surfaces as
        # a wrong number. Neither account has linked an analysis here, so both
        # must report an empty log rather than each other's.
        for label, headers in (("A", headers_a), ("B", headers_b)):
            calibration = client.get("/api/ai/calibration", headers=headers).json()
            check(
                calibration["linked"] == 0 and calibration["corrected"] == 0,
                f"{label}'s calibration counts only {label}",
            )

        b_export = client.get("/api/data/export", headers=headers_b).text
        check("Smoke Beta One" in b_export, "B's export has B's meal")
        check("Smoke Alpha" not in b_export, "B's export excludes A's meals")

        # -- Direct-ID probing: B attacks A's concrete resource ids -----------
        response = client.delete(f"/api/meals/{a_meal_ids[0]}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's meal id -> 404")
        response = client.delete(f"/api/foods/{a_food_id}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's food id -> 404")
        response = client.put(
            f"/api/foods/{a_food_id}",
            json={**food, "name": "Renamed By B", "calories": 999},
            headers=headers_b,
        )
        check(response.status_code == 404, "B PUT A's food id -> 404")
        response = client.delete(f"/api/weights/{a_weight_id}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's weight id -> 404")
        response = client.delete(
            f"/api/meal-templates/{a_template_id}", headers=headers_b
        )
        check(response.status_code == 404, "B DELETE A's template id -> 404")
        response = client.delete(f"/api/water/{a_water_id}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's water id -> 404")
        response = client.delete(
            "/api/steps", params={"date": step_day}, headers=headers_b
        )
        check(response.status_code == 204, "B DELETE B's own step day -> 204")
        a_steps = client.get(
            "/api/steps", params={"date": step_day}, headers=headers_a
        ).json()
        check(
            a_steps["steps"] == 4000 and a_steps["logged"] is True,
            "A's step day survived B clearing the same date",
        )
        # Re-logged because there is no id to probe with -- /api/steps is
        # addressed by date, so B clearing its *own* day is the only way to
        # test the scoping, and the DB check below still expects a row each.
        client.post(
            "/api/steps",
            json={"date": step_day, "steps": 12500},
            headers=headers_b,
        )
        response = client.delete(
            f"/api/supplements/{a_supplement_id}", headers=headers_b
        )
        check(response.status_code == 404, "B DELETE A's supplement id -> 404")
        response = client.post(
            "/api/supplements/log",
            json={"supplement_id": a_supplement_id, "date": dose_day, "time": "08:00"},
            headers=headers_b,
        )
        check(response.status_code == 404, "B tick A's supplement id -> 404")
        response = client.delete(
            "/api/supplements/log",
            params={"supplement_id": a_supplement_id, "date": dose_day,
                    "time": "08:00"},
            headers=headers_b,
        )
        check(response.status_code == 404, "B untick A's supplement id -> 404")
        a_doses = client.get(
            "/api/supplements/day", params={"date": dose_day}, headers=headers_a
        ).json()
        check(a_doses["taken"] == 1, "A's dose survived B's three attempts")
        response = client.delete(f"/api/plan/{plan_event}", headers=headers_b)
        check(response.status_code == 204, "B cancels B's own plan -> 204")
        a_plan_day = client.get(
            "/api/plan/day", params={"date": plan_event}, headers=headers_a
        ).json()
        check(
            a_plan_day["calorie_delta"] == 400,
            "A's plan survived B cancelling the same event date",
        )
        # Re-created for the same reason B's step day is re-logged above: a plan
        # is addressed by date rather than id, so B cancelling its own is the
        # only way to probe the scoping, and the DB check below expects a row
        # for each account.
        client.post(
            "/api/plan",
            json={"kind": "planned", "event_date": plan_event,
                  "dates": [plan_fund], "calorie_delta": 600},
            headers=headers_b,
        )
        response = client.patch(
            "/api/ai/analyses/999999", json={"meal_id": b_meal_id}, headers=headers_b
        )
        check(response.status_code == 404, "B PATCH unknown analysis -> 404")

        # A's data survived the probing intact.
        a_after = {m["id"] for m in client.get("/api/meals", headers=headers_a).json()}
        check(a_after == set(a_meal_ids), "A's meals unchanged after B's probing")
        a_foods_after = client.get("/api/foods", headers=headers_a).json()
        check(
            [f["id"] for f in a_foods_after] == [a_food_id]
            and a_foods_after[0]["calories"] == 100,
            "A's food unchanged after B's probing",
        )

        # -- CSV import duplicate check does not cross users -------------------
        csv_row = "date,name,calories,protein\n2026-07-01,Smoke Alpha One,500,40\n"
        result = client.post(
            "/api/data/import",
            files={"file": ("dup.csv", csv_row, "text/csv")},
            headers=headers_b,
        ).json()
        check(result["inserted"] == 1, "row identical to A's meal imports fresh for B")
        result = client.post(
            "/api/data/import",
            files={"file": ("dup.csv", csv_row, "text/csv")},
            headers=headers_a,
        ).json()
        check(result["skipped_duplicates"] == 1, "same row IS a duplicate for A")

        # -- Optional: row-level ownership straight from the database ----------
        if os.environ.get("DATABASE_URL"):
            from sqlalchemy import create_engine, select
            from sqlalchemy.orm import Session

            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from app.models import (
                CaloriePlanDay, Food, Meal, MealTemplate, Setting, StepEntry,
                Supplement, SupplementLog, WaterLog, WeightEntry,
            )

            engine = create_engine(os.environ["DATABASE_URL"])
            with Session(engine) as session:
                # A: 2 created (import was a duplicate); B: 1 created + 1 imported.
                for uid, expected in ((user_a["id"], 2), (user_b["id"], 2)):
                    rows = session.scalars(select(Meal).where(Meal.user_id == uid)).all()
                    check(len(rows) == expected, f"DB: user {uid} owns {expected} meals")
                foods = session.scalars(
                    select(Food).where(Food.user_id.in_([user_a["id"], user_b["id"]]))
                ).all()
                check(
                    sorted(f.user_id for f in foods) == sorted([user_a["id"], user_b["id"]]),
                    "DB: one food row per user, correctly owned",
                )
                weigh_ins = session.scalars(
                    select(WeightEntry).where(
                        WeightEntry.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(w.user_id for w in weigh_ins)
                    == sorted([user_a["id"], user_b["id"]]),
                    "DB: one weigh-in row per user on the shared date",
                )
                templates = session.scalars(
                    select(MealTemplate).where(
                        MealTemplate.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(t.user_id for t in templates)
                    == sorted([user_a["id"], user_b["id"]]),
                    "DB: one template row per user despite the shared name",
                )
                water = session.scalars(
                    select(WaterLog).where(
                        WaterLog.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(w.user_id for w in water)
                    == sorted([user_a["id"], user_b["id"]]),
                    "DB: one water row per user on the shared date",
                )
                steps_rows = session.scalars(
                    select(StepEntry).where(
                        StepEntry.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(s.user_id for s in steps_rows)
                    == sorted([user_a["id"], user_b["id"]]),
                    "DB: one steps row per user on the shared date",
                )
                supplements = session.scalars(
                    select(Supplement).where(
                        Supplement.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(s.user_id for s in supplements)
                    == sorted([user_a["id"], user_b["id"]]),
                    "DB: one supplement row per user despite the shared name",
                )
                plan_rows = session.scalars(
                    select(CaloriePlanDay).where(
                        CaloriePlanDay.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    sorted(r.user_id for r in plan_rows)
                    == sorted([user_a["id"]] * 2 + [user_b["id"]] * 2),
                    "DB: two plan rows per user on the shared event date",
                )
                dose_rows = session.scalars(
                    select(SupplementLog).where(
                        SupplementLog.user_id.in_([user_a["id"], user_b["id"]])
                    )
                ).all()
                check(
                    [log.user_id for log in dose_rows] == [user_a["id"]],
                    "DB: the only dose row belongs to A, despite B's attempts",
                )
                for uid in (user_a["id"], user_b["id"]):
                    check(
                        session.get(Setting, uid) is not None,
                        f"DB: settings row exists for user {uid}",
                    )
            engine.dispose()
        else:
            print("  [skip] DATABASE_URL not set — DB row checks skipped")

        # -- Cleanup (accounts remain; see module docstring) --------------------
        for meal_id in a_meal_ids:
            client.delete(f"/api/meals/{meal_id}", headers=headers_a)
        client.delete(f"/api/meals/{b_meal_id}", headers=headers_b)
        client.delete(f"/api/foods/{a_food_id}", headers=headers_a)
        client.delete(f"/api/foods/{b_food_id}", headers=headers_b)
        client.delete(f"/api/weights/{a_weight_id}", headers=headers_a)
        client.delete(f"/api/weights/{b_weight_id}", headers=headers_b)
        client.delete(f"/api/meal-templates/{a_template_id}", headers=headers_a)
        client.delete(f"/api/meal-templates/{b_template_id}", headers=headers_b)
        client.delete(f"/api/water/{a_water_id}", headers=headers_a)
        client.delete(f"/api/water/{b_water_id}", headers=headers_b)
        client.delete("/api/steps", params={"date": step_day}, headers=headers_a)
        client.delete("/api/steps", params={"date": step_day}, headers=headers_b)
        client.delete(f"/api/plan/{plan_event}", headers=headers_a)
        client.delete(f"/api/plan/{plan_event}", headers=headers_b)
        # The dose rows go with the supplements by CASCADE, which is worth
        # leaning on here rather than deleting them separately: if the cascade
        # were missing, the next run's DB check would find an orphan.
        client.delete(f"/api/supplements/{a_supplement_id}", headers=headers_a)
        client.delete(f"/api/supplements/{b_supplement_id}", headers=headers_b)
        # B's imported duplicate meal
        for meal in client.get("/api/meals", headers=headers_b).json():
            client.delete(f"/api/meals/{meal['id']}", headers=headers_b)
        for meal in client.get("/api/meals", headers=headers_a).json():
            client.delete(f"/api/meals/{meal['id']}", headers=headers_a)

    print(f"\nAll {_checks} checks passed against {BASE_URL}")
    print("Note: throwaway smoke-* accounts remain; delete them from Settings.")


if __name__ == "__main__":
    main()
