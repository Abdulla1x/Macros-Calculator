"""Live two-account isolation smoke test.

Runs against a real, running deployment (local or production) and proves via
direct API calls that two accounts cannot see or modify each other's data.

Usage:
    BASE_URL=http://localhost:8000 python scripts/smoke_multiuser.py
    BASE_URL=https://<service>.onrender.com python scripts/smoke_multiuser.py

If DATABASE_URL is also set, the script additionally connects to the database
and asserts row-level ownership directly.

Leaves behind the two throwaway accounts (there is no delete-account endpoint
yet); their data is removed via the API where possible.
"""
import os
import sys
import uuid

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
            ("GET", "/api/settings"),
            ("GET", "/api/analytics/daily"),
            ("GET", "/api/data/export"),
            ("POST", "/api/ai/analyze"),
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

        client.put(
            "/api/settings",
            json={"calorie_goal": 1750, "protein_goal": 155, "carbs_goal": 200,
                  "fat_goal": 55, "track_carbs": True, "track_fat": False},
            headers=headers_a,
        )

        # -- Read isolation ----------------------------------------------------
        a_names = {m["name"] for m in client.get("/api/meals", headers=headers_a).json()}
        b_names = {m["name"] for m in client.get("/api/meals", headers=headers_b).json()}
        check(a_names == {"Smoke Alpha One", "Smoke Alpha Two"}, "A sees only A's meals")
        check(b_names == {"Smoke Beta One"}, "B sees only B's meals")

        b_foods = client.get("/api/foods", headers=headers_b).json()
        check([f["id"] for f in b_foods] == [b_food_id], "B sees only B's foods")
        check(b_foods[0]["calories"] == 999, "B's upsert did not touch A's food")

        b_settings = client.get("/api/settings", headers=headers_b).json()
        check(b_settings["calorie_goal"] == 2000, "A's settings change invisible to B")

        b_analytics = client.get("/api/analytics/daily", headers=headers_b).json()
        check(b_analytics["totals"]["calories"] == 300, "B's analytics count only B")

        b_export = client.get("/api/data/export", headers=headers_b).text
        check("Smoke Beta One" in b_export, "B's export has B's meal")
        check("Smoke Alpha" not in b_export, "B's export excludes A's meals")

        # -- Direct-ID probing: B attacks A's concrete resource ids -----------
        response = client.delete(f"/api/meals/{a_meal_ids[0]}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's meal id -> 404")
        response = client.delete(f"/api/foods/{a_food_id}", headers=headers_b)
        check(response.status_code == 404, "B DELETE A's food id -> 404")
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
            from app.models import Food, Meal, Setting

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
        # B's imported duplicate meal
        for meal in client.get("/api/meals", headers=headers_b).json():
            client.delete(f"/api/meals/{meal['id']}", headers=headers_b)
        for meal in client.get("/api/meals", headers=headers_a).json():
            client.delete(f"/api/meals/{meal['id']}", headers=headers_a)

    print(f"\nAll {_checks} checks passed against {BASE_URL}")
    print("Note: throwaway smoke-* accounts remain (no delete-account endpoint yet).")


if __name__ == "__main__":
    main()
