"""Supplements: the list, the daily check-offs, and the history rules.

Dates are relative to today because the log validator rejects future dates, so
a fixed calendar date would eventually start failing on its own -- the same
reason test_steps.py, test_water.py and test_weights.py do it.

The interesting half of this file is not the CRUD. It is the four tests that
pin what happens to a *past* day when the schedule changes underneath it, since
that is the part a reasonable-looking refactor would quietly break.
"""
from datetime import date, timedelta
from pathlib import Path

from app.routers import supplements as app_supplements
from app.schemas import MAX_SUPPLEMENTS
from conftest import utc_today


def days_ago(n: int) -> str:
    """A day in the past, measured on the clock the *server* compares against.

    `_day`'s rule 1 skips a supplement whose `created_at.date()` is after the
    day being asked about, and `created_at` is naive UTC. Counting back from the
    local date instead would, at a positive UTC offset, hand back a "yesterday"
    that is still today in UTC -- so the supplement counts as scheduled and a
    test about a settled past day sees a live one. Same clock, same answer,
    everywhere.
    """
    return (utc_today() - timedelta(days=n)).isoformat()


def add(client, name="Vitamin D", dose="5000 IU", times=("08:00",), active=True):
    return client.post(
        "/api/supplements",
        json={"name": name, "dose": dose, "times": list(times), "active": active},
    )


def tick(client, supplement_id: int, time: str = "08:00", day: str | None = None):
    return client.post(
        "/api/supplements/log",
        json={
            "supplement_id": supplement_id,
            "date": day or date.today().isoformat(),
            "time": time,
        },
    )


def untick(client, supplement_id: int, time: str = "08:00", day: str | None = None):
    return client.delete(
        "/api/supplements/log",
        params={
            "supplement_id": supplement_id,
            "date": day or date.today().isoformat(),
            "time": time,
        },
    )


def day(client, when: str | None = None):
    params = {"date": when} if when else {}
    return client.get("/api/supplements/day", params=params).json()


# --- The list ----------------------------------------------------------------


def test_add_list_edit_and_delete(client):
    created = add(client)
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Vitamin D"
    assert body["dose"] == "5000 IU"
    assert body["times"] == ["08:00"]
    assert body["active"] is True

    assert [s["name"] for s in client.get("/api/supplements").json()] == ["Vitamin D"]

    edited = client.put(
        f"/api/supplements/{body['id']}",
        json={
            "name": "Vitamin D3",
            "dose": "4000 IU",
            "times": ["09:00", "21:00"],
            "active": False,
        },
    )
    assert edited.status_code == 200
    assert edited.json()["times"] == ["09:00", "21:00"]
    assert edited.json()["active"] is False

    assert client.delete(f"/api/supplements/{body['id']}").status_code == 204
    assert client.get("/api/supplements").json() == []


def test_a_paused_supplement_is_still_listed(client):
    """Otherwise pausing would be a one-way door.

    The Settings editor is the only place to un-pause, and it reads this list.
    The dashboard card reads /day instead, which is where `active` applies.
    """
    created = add(client, active=False).json()
    assert [s["id"] for s in client.get("/api/supplements").json()] == [created["id"]]


def test_duplicate_names_are_refused_case_insensitively(client):
    add(client, name="Magnesium")
    clash = add(client, name="  magnesium  ")
    assert clash.status_code == 409
    assert "magnesium" in clash.json()["detail"].lower()


def test_renaming_onto_an_existing_name_is_refused(client):
    add(client, name="Magnesium")
    other = add(client, name="Zinc").json()
    clash = client.put(
        f"/api/supplements/{other['id']}",
        json={"name": "MAGNESIUM", "dose": None, "times": ["08:00"], "active": True},
    )
    assert clash.status_code == 409


def test_the_list_is_capped(client):
    for n in range(MAX_SUPPLEMENTS):
        assert add(client, name=f"Supplement {n}").status_code == 201
    over = add(client, name="One too many")
    assert over.status_code == 422
    assert str(MAX_SUPPLEMENTS) in over.json()["detail"]


def test_times_are_sorted_and_deduplicated(client):
    body = add(client, times=["20:00", "08:00", "20:00"]).json()
    # De-duplicated because the log's unique index spans exactly this value:
    # a repeated time is a dose that could never be ticked separately.
    assert body["times"] == ["08:00", "20:00"]


def test_bad_input_is_refused(client):
    assert add(client, times=["25:00"]).status_code == 422
    assert add(client, times=["8:00"]).status_code == 422
    assert add(client, times=[]).status_code == 422
    assert add(client, times=["08:00"] * 7).status_code == 422
    assert add(client, name="   ").status_code == 422
    assert add(client, name="x" * 101).status_code == 422


def test_a_blank_dose_stores_as_no_dose(client):
    """Two ways to say "unset" in one column is how a stray separator appears
    in a display that nobody can find the source of."""
    assert add(client, dose="   ").json()["dose"] is None


def test_a_future_dose_cannot_be_ticked(client):
    created = add(client).json()
    ahead = (date.today() + timedelta(days=3)).isoformat()
    assert tick(client, created["id"], day=ahead).status_code == 422


# --- The day -----------------------------------------------------------------


def test_a_day_with_no_supplements_is_empty_not_an_error(client):
    body = day(client)
    assert body["slots"] == []
    assert body["taken"] == 0
    assert body["scheduled"] == 0


def test_tick_and_untick(client):
    created = add(client, times=["08:00", "20:00"]).json()

    fresh = day(client)
    assert fresh["scheduled"] == 2
    assert fresh["taken"] == 0
    assert [slot["time"] for slot in fresh["slots"]] == ["08:00", "20:00"]

    ticked = tick(client, created["id"], "08:00")
    assert ticked.status_code == 200
    assert ticked.json()["taken"] == 1
    assert ticked.json()["slots"][0]["taken"] is True

    cleared = untick(client, created["id"], "08:00")
    assert cleared.status_code == 200
    assert cleared.json()["taken"] == 0


def test_ticking_twice_is_the_same_fact(client):
    """A tick is a state, not an event -- the opposite of a glass of water.

    A double-tap on a laggy connection must not record one pill as two, and
    must not surface a 409 the user cannot act on: the box was already ticked,
    which is exactly what they asked for.
    """
    created = add(client).json()
    assert tick(client, created["id"]).status_code == 200
    again = tick(client, created["id"])
    assert again.status_code == 200
    assert again.json()["taken"] == 1


def test_unticking_an_untaken_dose_is_not_an_error(client):
    created = add(client).json()
    cleared = untick(client, created["id"])
    assert cleared.status_code == 200
    assert cleared.json()["taken"] == 0


def test_slots_are_ordered_by_time_then_name(client):
    add(client, name="Zinc", times=["21:00"])
    add(client, name="Creatine", times=["08:00"])
    add(client, name="Ashwagandha", times=["21:00"])
    order = [(s["time"], s["name"]) for s in day(client)["slots"]]
    assert order == [
        ("08:00", "Creatine"),
        ("21:00", "Ashwagandha"),
        ("21:00", "Zinc"),
    ]


def test_a_paused_supplement_leaves_the_card(client):
    created = add(client).json()
    client.put(
        f"/api/supplements/{created['id']}",
        json={"name": "Vitamin D", "dose": None, "times": ["08:00"], "active": False},
    )
    assert day(client)["slots"] == []


def test_ticking_another_time_than_scheduled_is_allowed(client):
    """A correction, not an error: you took it, just not when you meant to."""
    created = add(client, times=["08:00"]).json()
    body = tick(client, created["id"], "13:00").json()
    assert body["taken"] == 1
    off = [slot for slot in body["slots"] if slot["time"] == "13:00"]
    assert off and off[0]["off_schedule"] is True


# --- What must not happen to a past day --------------------------------------


def test_a_new_supplement_does_not_backfill_missed_doses(client):
    """Adding creatine today must not mark last week as five days of failure.

    This is the class of bug the roadmap keeps paying for: a number that reads
    as failure when the honest answer is "not applicable".
    """
    add(client)
    assert day(client, days_ago(3))["scheduled"] == 0
    assert day(client)["scheduled"] == 1


def test_pausing_leaves_a_past_day_fully_taken(client):
    """Yesterday's dose was taken. Stopping today cannot un-take it."""
    created = add(client).json()
    yesterday = days_ago(1)
    tick(client, created["id"], "08:00", day=yesterday)

    client.put(
        f"/api/supplements/{created['id']}",
        json={"name": "Vitamin D", "dose": None, "times": ["08:00"], "active": False},
    )

    past = day(client, yesterday)
    assert past["taken"] == 1
    assert past["scheduled"] == 1
    assert past["slots"][0]["off_schedule"] is True


def test_rescheduling_leaves_a_past_day_fully_taken(client):
    """Moving the morning dose 08:00 -> 09:00 must not invent a missed dose.

    Without the union rule this reads "1 of 2" for a day on which exactly one
    dose was scheduled and exactly one was taken.
    """
    created = add(client, times=["08:00"]).json()
    yesterday = days_ago(1)
    tick(client, created["id"], "08:00", day=yesterday)

    client.put(
        f"/api/supplements/{created['id']}",
        json={"name": "Vitamin D", "dose": None, "times": ["09:00"], "active": True},
    )

    past = day(client, yesterday)
    assert past["taken"] == 1
    assert past["scheduled"] == 1
    assert past["slots"][0]["time"] == "08:00"
    assert past["slots"][0]["off_schedule"] is True

    # Today still schedules the new time, untaken.
    today = day(client)
    assert [(s["time"], s["taken"]) for s in today["slots"]] == [("09:00", False)]


def test_deleting_a_supplement_takes_its_doses_with_it(client):
    created = add(client).json()
    tick(client, created["id"])
    other = add(client, name="Zinc", times=["21:00"]).json()
    tick(client, other["id"], "21:00")

    client.delete(f"/api/supplements/{created['id']}")

    remaining = day(client)
    assert remaining["scheduled"] == 1
    assert remaining["taken"] == 1
    assert remaining["slots"][0]["name"] == "Zinc"


# --- The rule the whole feature must not break -------------------------------


def test_supplements_router_never_recomputes_targets():
    """Phase 5's guarantee, defended at the source rather than the behaviour.

    The third sibling of test_water.py's and test_steps.py's versions. A
    value-level test cannot do this job: supplements are not an input to any
    target, so calling apply_auto_targets here would recompute the goals and
    land on exactly the same numbers -- "never called" and "called, no change
    today" are indistinguishable from outside, right up until something makes
    them differ.

    Checked against a deliberately broken source before being trusted.
    """
    source = Path(app_supplements.__file__).read_text()
    body = source.split('"""', 2)[2]  # skip the module docstring, which names it
    assert "apply_auto_targets" not in body


def test_ticking_a_dose_leaves_the_stored_goals_alone(client):
    """The observable half of the rule above. Weaker, and kept for that reason."""
    client.put(
        "/api/settings",
        json={
            "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
            "fat_goal": 70, "track_carbs": False, "track_fat": False,
            "height_cm": 180.0, "birth_date": "1990-05-04", "sex": "male",
            "activity_level": "moderate", "goal_rate_kg_per_week": -0.5,
            "targets_auto": True,
        },
    )
    client.post("/api/weights", json={"date": days_ago(1), "weight_kg": 80.0})
    before = client.get("/api/settings").json()

    created = add(client).json()
    tick(client, created["id"])

    assert client.get("/api/settings").json() == before


# --- The export promise ------------------------------------------------------


def test_the_full_export_carries_both_tables(client):
    created = add(client, name="Creatine", dose="5 g", times=["08:00", "20:00"]).json()
    tick(client, created["id"], "08:00")

    export = client.get("/api/data/export/all").json()
    assert export["supplements"] == [
        {
            "name": "Creatine",
            "dose": "5 g",
            "times": ["08:00", "20:00"],
            "active": True,
            "created_at": export["supplements"][0]["created_at"],
        }
    ]
    log = export["supplement_logs"][0]
    # Named, not id'd: an id means nothing outside the database it came from.
    assert log["supplement"] == "Creatine"
    assert log["time"] == "08:00"
