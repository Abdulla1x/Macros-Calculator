from app.routers.meals import RECENT_SCAN_ROWS
from conftest import post_raw_json


def _sample(**overrides):
    meal = {
        "date": "2026-07-01",
        "name": "Chicken & Rice",
        "calories": 560,
        "protein": 45,
        "carbs": 56,
        "fat": 8.5,
    }
    meal.update(overrides)
    return meal


def test_create_and_list_by_date(client):
    created = client.post("/api/meals", json=_sample()).json()
    assert created["id"] > 0

    client.post("/api/meals", json=_sample(date="2026-07-02", name="Other Day"))

    meals = client.get("/api/meals", params={"date": "2026-07-01"}).json()
    assert len(meals) == 1
    assert meals[0]["name"] == "Chicken & Rice"
    assert meals[0]["carbs"] == 56


def test_optional_macros_can_be_omitted(client):
    response = client.post(
        "/api/meals",
        json={"date": "2026-07-01", "name": "Simple", "calories": 300, "protein": 20},
    )
    assert response.status_code == 201
    assert response.json()["carbs"] is None


def test_rejects_negative_and_blank(client):
    assert client.post("/api/meals", json=_sample(calories=-5)).status_code == 422
    assert client.post("/api/meals", json=_sample(name="")).status_code == 422


def test_rejects_non_finite_macros(client):
    """Positive infinity is the one `ge=0` let through: `inf >= 0` is True.

    (`nan` and `-inf` were already refused by the bound itself.) Stored, one such
    value breaks the account two ways at once — GET /api/data/export/all 500s,
    because it returns a plain dict whose raw float meets Starlette's
    allow_nan=False, while GET /api/meals quietly reports `null` for a field
    types.ts declares as `number`.
    """
    for field in ("calories", "protein", "carbs", "fat"):
        for bad in (float("inf"), float("-inf"), float("nan")):
            response = post_raw_json(client, "/api/meals", _sample(**{field: bad}))
            assert response.status_code == 422, f"{field}={bad} was accepted"


def test_the_rejection_itself_renders(client):
    """Regression for the 422-that-500s, now reachable outside templates.

    FastAPI echoes the rejected value back under `input`, and Starlette
    serializes the body with allow_nan=False — so rendering this particular
    rejection used to crash. main.py's validation_error_handler is what fixes
    it; this is the first meals-side test that depends on it.
    """
    response = post_raw_json(client, "/api/meals", _sample(calories=float("inf")))
    assert response.status_code == 422
    assert "detail" in response.json()


def test_update_meal(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]

    response = client.put(
        f"/api/meals/{meal_id}",
        json=_sample(date="2026-07-03", name="  Chicken & Quinoa ", calories=610, fat=None),
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == meal_id
    assert updated["date"] == "2026-07-03"
    assert updated["name"] == "Chicken & Quinoa"
    assert updated["calories"] == 610
    assert updated["fat"] is None

    # The update moved the meal, not copied it.
    assert client.get("/api/meals", params={"date": "2026-07-01"}).json() == []
    assert [m["id"] for m in client.get("/api/meals").json()] == [meal_id]


def test_updated_at_is_null_until_the_meal_is_edited(client):
    created = client.post("/api/meals", json=_sample()).json()
    # A meal nobody has corrected has no edit time. Defaulting this to the
    # creation time would report every meal in the table as revised.
    assert created["updated_at"] is None

    edited = client.put(f"/api/meals/{created['id']}", json=_sample(calories=610)).json()
    assert edited["updated_at"] is not None

    # And it survives the round trip -- the stamp is stored, not just returned.
    listed = client.get("/api/meals", params={"date": "2026-07-01"}).json()
    assert listed[0]["updated_at"] == edited["updated_at"]


def test_editing_does_not_rewrite_when_the_meal_was_logged(client):
    created = client.post("/api/meals", json=_sample()).json()
    exported_before = client.get("/api/data/export/all").json()["meals"][0]

    client.put(f"/api/meals/{created['id']}", json=_sample(calories=610))
    exported_after = client.get("/api/data/export/all").json()["meals"][0]

    # A correction changes when the row last changed, never when the food was
    # first logged -- created_at is the usage signal and must not drift.
    assert exported_after["created_at"] == exported_before["created_at"]
    assert exported_before["updated_at"] is None
    assert exported_after["updated_at"] is not None


def test_update_meal_validates_and_404s(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]
    assert client.put(f"/api/meals/{meal_id}", json=_sample(calories=-5)).status_code == 422
    assert client.put(f"/api/meals/{meal_id}", json=_sample(name="")).status_code == 422
    assert client.put("/api/meals/99999", json=_sample()).status_code == 404


def test_delete_meal(client):
    meal_id = client.post("/api/meals", json=_sample()).json()["id"]
    assert client.delete(f"/api/meals/{meal_id}").status_code == 204
    assert client.delete(f"/api/meals/{meal_id}").status_code == 404
    assert client.get("/api/meals", params={"date": "2026-07-01"}).json() == []


def test_list_rejects_malformed_date(client):
    assert client.get("/api/meals", params={"date": "garbage"}).status_code == 422
    assert client.get("/api/meals", params={"date": "2026-13-40"}).status_code == 422


def test_undated_list_is_capped_and_newest_first(client):
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        client.post("/api/meals", json=_sample(date=day, name=f"Meal {day}"))

    meals = client.get("/api/meals", params={"limit": 2}).json()
    assert [m["date"] for m in meals] == ["2026-07-03", "2026-07-02"]
    assert client.get("/api/meals", params={"limit": 0}).status_code == 422
    assert client.get("/api/meals", params={"limit": 5000}).status_code == 422


# --- /api/meals/recent -------------------------------------------------------
#
# "Recently logged": the most recent meal under each distinct name. Saved meals
# cover the meal you thought to store in advance; this covers the one you ate on
# Tuesday and did not.


def test_recent_is_newest_first(client):
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        client.post("/api/meals", json=_sample(date=day, name=f"Meal {day}"))

    recent = client.get("/api/meals/recent").json()
    assert [m["date"] for m in recent] == ["2026-07-03", "2026-07-02", "2026-07-01"]


def test_recent_keeps_only_the_newest_meal_of_each_name(client):
    # The same name on two days with different numbers. Which row survives is
    # the whole question: offering Monday's figures under a name last eaten on
    # Tuesday would be the list quietly answering a question nobody asked.
    client.post("/api/meals", json=_sample(date="2026-07-01", calories=400))
    client.post("/api/meals", json=_sample(date="2026-07-02", calories=650))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Salad"))

    recent = client.get("/api/meals/recent").json()
    assert [(m["name"], m["calories"], m["date"]) for m in recent] == [
        ("Salad", 560, "2026-07-02"),
        ("Chicken & Rice", 650, "2026-07-02"),
    ]


def test_recent_dedupes_case_insensitively(client):
    client.post("/api/meals", json=_sample(date="2026-07-01", name="Breakfast"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="breakfast"))
    client.post("/api/meals", json=_sample(date="2026-07-03", name="  BREAKFAST  "))

    recent = client.get("/api/meals/recent").json()
    # Stored stripped by create_meal, so the survivor is the third row's name
    # rather than its untrimmed input.
    assert [m["name"] for m in recent] == ["BREAKFAST"]


def test_recent_honours_limit_and_rejects_an_impossible_one(client):
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        client.post("/api/meals", json=_sample(date=day, name=f"Meal {day}"))

    assert len(client.get("/api/meals/recent", params={"limit": 2}).json()) == 2
    assert client.get("/api/meals/recent", params={"limit": 0}).status_code == 422
    assert client.get("/api/meals/recent", params={"limit": 500}).status_code == 422


def test_recent_is_empty_for_an_account_that_has_logged_nothing(client):
    response = client.get("/api/meals/recent")
    assert response.status_code == 200
    assert response.json() == []


def test_recent_is_not_read_as_a_meal_id(client):
    # `/recent` sits above the `/{meal_id}` routes. Nothing routes GET on a path
    # parameter today, so this asserts the arrangement rather than a near miss:
    # it is what would fail if a later `GET /{meal_id}` were declared first.
    assert client.get("/api/meals/recent").status_code == 200


def test_recent_stops_at_the_scan_window(client):
    """The bounded scan has a visible consequence, and it is the intended one.

    A name that falls outside RECENT_SCAN_ROWS is not offered, however few
    distinct names the account has. That is the cost of not reading an unbounded
    history on every dashboard load, and it is worth pinning: without this test
    the constant looks like a number nobody chose, and raising or dropping it
    would break nothing.
    """
    client.post("/api/meals", json=_sample(date="2026-06-01", name="Ancient Salad"))
    for _ in range(RECENT_SCAN_ROWS):
        client.post("/api/meals", json=_sample(date="2026-07-01", name="Breakfast"))

    names = [m["name"] for m in client.get("/api/meals/recent").json()]
    assert names == ["Breakfast"]


def test_recent_demotes_names_already_logged_on_the_viewed_day(client):
    """The card offers what you have NOT got round to logging, first.

    Without this the dashboard offered six cells every one of which said
    "Today", because the newest distinct names on a day you have logged six
    meals ARE those six meals -- each one already listed in full further down
    the same page.
    """
    client.post("/api/meals", json=_sample(date="2026-07-01", name="Beef Stew"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Tea"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Boiled Eggs"))

    plain = [m["name"] for m in client.get("/api/meals/recent").json()]
    assert plain == ["Boiled Eggs", "Tea", "Beef Stew"]

    demoted = client.get(
        "/api/meals/recent", params={"demote_date": "2026-07-02"}
    ).json()
    assert [m["name"] for m in demoted] == ["Beef Stew", "Boiled Eggs", "Tea"]


def test_recent_demotes_rather_than_dropping(client):
    """Demoted, not excluded -- people eat the same thing twice in a day.

    Every name here was logged on the demoted day, so an implementation that
    filtered would return nothing at all and the card would vanish on exactly
    the day it is most used.
    """
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Tea"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Boiled Eggs"))

    names = [
        m["name"]
        for m in client.get(
            "/api/meals/recent", params={"demote_date": "2026-07-02"}
        ).json()
    ]
    assert sorted(names) == ["Boiled Eggs", "Tea"]


def test_recent_without_demote_date_is_unchanged(client):
    """A client that has never heard of the parameter gets what it always got."""
    client.post("/api/meals", json=_sample(date="2026-07-01", name="Beef Stew"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Tea"))

    assert [m["name"] for m in client.get("/api/meals/recent").json()] == [
        "Tea",
        "Beef Stew",
    ]


def test_recent_demotes_before_applying_the_limit(client):
    """The consequence that decides WHERE this rule can live.

    The first attempt at this reordered the response in the browser instead,
    and did nothing: deduplication caps the list at `limit` first, so on a day
    with `limit` distinct names of its own the older names are already gone by
    the time any client sees them. Here two meals are logged on the viewed day
    and one earlier; at limit=2 a downstream sort can only ever return the two
    from that day, while demoting first surfaces the older one.
    """
    client.post("/api/meals", json=_sample(date="2026-07-01", name="Beef Stew"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Tea"))
    client.post("/api/meals", json=_sample(date="2026-07-02", name="Boiled Eggs"))

    names = [
        m["name"]
        for m in client.get(
            "/api/meals/recent",
            params={"limit": 2, "demote_date": "2026-07-02"},
        ).json()
    ]
    assert names[0] == "Beef Stew"
    assert len(names) == 2


def test_recent_refuses_a_demote_date_that_is_not_a_date(client):
    assert (
        client.get("/api/meals/recent", params={"demote_date": "yesterday"}).status_code
        == 422
    )


def test_a_copied_meal_is_a_new_row_logged_now(client):
    """The copy path's two dates, asserted rather than assumed.

    `date` is when the food was eaten and `created_at` is when the row was
    written -- the column comments on `models.py` exist because those answer
    different questions. Copying a meal to today must move the first and stamp
    the second afresh, or the copy would report the original's history.
    """
    source = client.post("/api/meals", json=_sample(date="2026-07-01")).json()

    copy = client.post(
        "/api/meals",
        json=_sample(date="2026-07-09", name=source["name"], calories=source["calories"]),
    ).json()

    assert copy["id"] != source["id"]
    assert copy["date"] == "2026-07-09"
    # Never edited, so it carries no edit stamp -- a copy is a new meal, not a
    # revision of the one it came from.
    assert copy["updated_at"] is None
    # The original is untouched by the copy.
    assert client.get("/api/meals?date=2026-07-01").json()[0]["id"] == source["id"]
