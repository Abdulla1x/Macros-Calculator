"""Admin metrics: who may read them, and what they must never contain."""
from datetime import date, datetime, timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app import keep_warm
from app.db import get_engine
from app.models import Meal, utcnow
from conftest import utc_today

ADMIN_ROUTES = ("/api/admin/stats", "/api/admin/users", "/api/admin/keep-warm")

TODAY = utc_today()
YESTERDAY = TODAY - timedelta(days=1)

# Deliberately distinctive so the privacy test can grep whole payloads for them
# rather than asserting the absence of a field name it has to know in advance.
SECRET_MEAL_NAME = "Zzyzx Clandestine Casserole"
SECRET_WEIGHT_KG = 83.7
SECRET_TEMPLATE_NAME = "Quixotic Ptarmigan Breakfast"
SECRET_INGREDIENT_NAME = "Vermillion Sprocket Oats"
# The body profile is the first genuinely personal data to land in the settings
# row -- someone's height, birth date and sex, not their choice of dinner. The
# metrics-only boundary has to cover it from the day it exists.
SECRET_HEIGHT_CM = 173.7
SECRET_BIRTH_DATE = "1987-03-19"
# Water is a count on the dashboard and never an amount: how much someone drank
# on a given day is content, the same way a weigh-in is. Both the entry and a
# custom goal are personal figures that live in the settings row.
SECRET_WATER_ML = 337.0
SECRET_WATER_GOAL_ML = 3137.0
# Steps are a count on the dashboard and never a figure: how far someone walked
# on a given day is content, exactly as a weigh-in or a water entry is. The
# goal lives in the settings row alongside the water one.
SECRET_STEPS = 31337
SECRET_STEPS_GOAL = 23117
# The most disclosive thing this app stores. A supplement list can name a
# prescription, so the name and the dose are both content in a way a step count
# is not -- an operator learning that an account tracks a named medication has
# learned something about that person's health. The dose string is asserted
# separately because it is a second field on the same row and would be the
# natural thing to "just include" for support purposes.
SECRET_SUPPLEMENT_NAME = "Borogove Wabe Extract"
SECRET_SUPPLEMENT_DOSE = "417 mcg"
# A calorie plan's event_date is disclosive in a way none of the above are: it
# says nothing about health and everything about a life -- that this person has
# something on a particular day. Far enough out that it cannot collide with a
# created_at or a signup date already in the payload.
SECRET_PLAN_EVENT_DATE = (TODAY + timedelta(days=137)).isoformat()
SECRET_PLAN_FUNDING_DATE = (TODAY + timedelta(days=139)).isoformat()


def email_of(client) -> str:
    return client.get("/api/auth/me").json()["email"]


def make_admin(client, monkeypatch, value: str | None = None) -> str:
    """Put this client's user on the allowlist and return their address.

    The address has to be read back at runtime: conftest numbers users from a
    session-wide counter, so which one this fixture got depends on test
    ordering. That this works at all is the point of reading ADMIN_EMAILS per
    request rather than at import.
    """
    address = email_of(client)
    monkeypatch.setenv("ADMIN_EMAILS", value if value is not None else address)
    return address


# --- Authorization -----------------------------------------------------------


def test_admin_routes_require_authentication(anon_client):
    for route in ADMIN_ROUTES:
        assert anon_client.get(route).status_code == 401, route


def test_nobody_is_admin_when_allowlist_is_unset(client):
    """The safe default, and the one that matters most: ADMIN_EMAILS is not
    committed anywhere, so a deploy that forgets it must lock everyone out."""
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 403, route


def test_nobody_is_admin_when_allowlist_is_blank(client, monkeypatch):
    for blank in ("", "   ", ",", " , ,"):
        monkeypatch.setenv("ADMIN_EMAILS", blank)
        for route in ADMIN_ROUTES:
            assert client.get(route).status_code == 403, (blank, route)


def test_allowlisted_user_reaches_admin_routes(client, monkeypatch):
    make_admin(client, monkeypatch)
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 200, route


def test_allowlist_matching_is_case_and_whitespace_tolerant(client, monkeypatch):
    address = email_of(client)
    make_admin(client, monkeypatch, f"  {address.upper()}  , other@example.com ")
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 200, route


def test_allowlist_tolerates_a_quoted_env_value(client, monkeypatch):
    """A value pasted into the Render dashboard with quotes around it."""
    address = email_of(client)
    make_admin(client, monkeypatch, f'"{address}"')
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 200, route


def test_non_admin_is_forbidden_while_admin_is_allowed(client, client_b, monkeypatch):
    make_admin(client, monkeypatch)
    for route in ADMIN_ROUTES:
        assert client.get(route).status_code == 200, route
        assert client_b.get(route).status_code == 403, route


def test_me_reports_the_admin_flag(client, client_b, monkeypatch):
    assert client.get("/api/auth/me").json()["is_admin"] is False

    make_admin(client, monkeypatch)
    # /me builds its UserOut through the same helper the token responses use.
    # Before that helper existed this returned False here and True on login,
    # because UserOut.is_admin has a default and the ORM row has no such
    # attribute -- so it failed silently rather than loudly.
    assert client.get("/api/auth/me").json()["is_admin"] is True
    assert client_b.get("/api/auth/me").json()["is_admin"] is False


def test_login_response_reports_the_admin_flag(client, anon_client, monkeypatch):
    from tests.conftest import TEST_PASSWORD

    address = make_admin(client, monkeypatch)
    login = anon_client.post(
        "/api/auth/login", json={"email": address, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["user"]["is_admin"] is True


# --- The privacy boundary ----------------------------------------------------


def test_admin_payloads_contain_no_user_content(client, client_b, monkeypatch):
    """Metrics only. If this fails, the README's scoping promise is false.

    Asserted against the raw response text rather than specific fields, so
    adding a content-bearing field anywhere in either payload trips it.
    """
    client_b.post(
        "/api/meals",
        json={
            "date": TODAY.isoformat(),
            "name": SECRET_MEAL_NAME,
            "calories": 500,
            "protein": 40,
        },
    )
    client_b.post(
        "/api/weights",
        json={"date": YESTERDAY.isoformat(), "weight_kg": SECRET_WEIGHT_KG},
    )
    client_b.post(
        "/api/foods",
        json={
            "name": SECRET_MEAL_NAME,
            "serving_size": 100,
            "calories": 165,
            "protein": 31,
        },
    )
    # A template carries user content twice over: its own name, and the name of
    # every ingredient inside it.
    client_b.post(
        "/api/meal-templates",
        json={
            "name": SECRET_TEMPLATE_NAME,
            "calories": 620,
            "protein": 48,
            "items": [
                {
                    "name": SECRET_INGREDIENT_NAME,
                    "weight_grams": 150,
                    "serving_size": 100,
                    "calories": 165,
                    "protein": 31,
                }
            ],
        },
    )

    client_b.post(
        "/api/water", json={"date": TODAY.isoformat(), "ml": SECRET_WATER_ML}
    )
    client_b.post(
        "/api/steps", json={"date": TODAY.isoformat(), "steps": SECRET_STEPS}
    )

    supplement = client_b.post(
        "/api/supplements",
        json={
            "name": SECRET_SUPPLEMENT_NAME,
            "dose": SECRET_SUPPLEMENT_DOSE,
            "times": ["08:00"],
            "active": True,
        },
    ).json()
    client_b.post(
        "/api/supplements/log",
        json={
            "supplement_id": supplement["id"],
            "date": TODAY.isoformat(),
            "time": "08:00",
        },
    )

    client_b.post(
        "/api/plan",
        json={
            "kind": "planned",
            "event_date": SECRET_PLAN_EVENT_DATE,
            "dates": [SECRET_PLAN_FUNDING_DATE],
            "calorie_delta": 400,
        },
    )

    client_b.put(
        "/api/settings",
        json={
            "calorie_goal": 2000, "protein_goal": 150, "carbs_goal": 250,
            "fat_goal": 70, "track_carbs": False, "track_fat": False,
            "height_cm": SECRET_HEIGHT_CM,
            "birth_date": SECRET_BIRTH_DATE,
            "sex": "female",
            "water_goal_ml": SECRET_WATER_GOAL_ML,
            "steps_goal": SECRET_STEPS_GOAL,
        },
    )

    make_admin(client, monkeypatch)
    for route in ADMIN_ROUTES:
        body = client.get(route).text
        assert SECRET_MEAL_NAME not in body, route
        assert str(SECRET_WEIGHT_KG) not in body, route
        assert SECRET_TEMPLATE_NAME not in body, route
        assert SECRET_INGREDIENT_NAME not in body, route
        assert str(SECRET_HEIGHT_CM) not in body, route
        assert SECRET_BIRTH_DATE not in body, route
        assert str(SECRET_WATER_ML) not in body, route
        assert str(SECRET_WATER_GOAL_ML) not in body, route
        assert str(SECRET_STEPS) not in body, route
        assert str(SECRET_STEPS_GOAL) not in body, route
        assert SECRET_SUPPLEMENT_NAME not in body, route
        assert SECRET_SUPPLEMENT_DOSE not in body, route
        assert SECRET_PLAN_EVENT_DATE not in body, route
        assert SECRET_PLAN_FUNDING_DATE not in body, route


# --- Metrics -----------------------------------------------------------------


def test_stats_counts_accounts_and_meals(client, client_b, monkeypatch):
    client_b.post(
        "/api/meals",
        json={
            "date": TODAY.isoformat(),
            "name": "Counted",
            "calories": 100,
            "protein": 10,
        },
    )
    make_admin(client, monkeypatch)

    stats = client.get("/api/admin/stats").json()
    assert stats["total_users"] == 2
    assert stats["total_meals"] == 1
    assert stats["signups_7d"] == 2
    # One account logged something; the admin account did not.
    assert stats["active_7d"] == 1
    assert stats["meals_7d"] == 1
    assert stats["ai_global_daily_limit"] > 0


def test_stats_series_cover_every_day_including_empty_ones(client, monkeypatch):
    """A chart fed only the days that have data draws a straight line across a
    gap, which reads as steady use during a week nobody opened the app."""
    make_admin(client, monkeypatch)
    stats = client.get("/api/admin/stats").json()

    assert len(stats["signups"]) == stats["window_days"]
    assert len(stats["activity"]) == stats["window_days"]
    assert stats["signups"][-1]["date"] == TODAY.isoformat()
    # Contiguous, one day apart, no holes.
    dates = [date.fromisoformat(point["date"]) for point in stats["activity"]]
    assert all(b - a == timedelta(days=1) for a, b in zip(dates, dates[1:]))


def test_user_rows_carry_counts_and_last_active(client, client_b, monkeypatch):
    client_b.post(
        "/api/meals",
        json={
            "date": TODAY.isoformat(),
            "name": "Counted",
            "calories": 100,
            "protein": 10,
        },
    )
    client_b.post(
        "/api/weights", json={"date": YESTERDAY.isoformat(), "weight_kg": 70.0}
    )
    client_b.post(
        "/api/meal-templates",
        json={"name": "Counted Template", "calories": 100, "protein": 10},
    )
    address_b = email_of(client_b)
    make_admin(client, monkeypatch)

    rows = {row["email"]: row for row in client.get("/api/admin/users").json()}
    assert rows[address_b]["meals"] == 1
    assert rows[address_b]["weights"] == 1
    assert rows[address_b]["foods"] == 0
    assert rows[address_b]["meal_templates"] == 1
    assert rows[address_b]["ai_calls"] == 0
    assert rows[address_b]["calorie_plan_days"] == 0
    assert rows[address_b]["last_active_at"] is not None


def test_planning_counts_rows_and_registers_as_activity(client, client_b, monkeypatch):
    """CaloriePlanDay is in _TIMESTAMPED, which is a claim worth checking.

    It passes that tuple's rule cleanly -- there is no update path, so every
    row's created_at is the moment a plan was actually made -- and MealTemplate
    and Supplement are both out of it for failing exactly that test. An
    assertion is cheaper than trusting the reasoning.
    """
    plan = client_b.post(
        "/api/plan",
        json={
            "kind": "planned",
            "event_date": (TODAY + timedelta(days=3)).isoformat(),
            "dates": [(TODAY + timedelta(days=i)).isoformat() for i in (4, 5)],
            "calorie_delta": 400,
        },
    )
    assert plan.status_code == 201, plan.text
    address_b = email_of(client_b)
    make_admin(client, monkeypatch)

    rows = {row["email"]: row for row in client.get("/api/admin/users").json()}
    # Rows, not plans: one banked day plus the two funding it.
    assert rows[address_b]["calorie_plan_days"] == 3
    assert rows[address_b]["last_active_at"] is not None


def test_last_active_is_null_for_an_account_that_did_nothing(client, monkeypatch):
    """Signed up and never came back is a real thing to want to see, so it has
    to be representable rather than a crash or a fake timestamp."""
    address = make_admin(client, monkeypatch)

    rows = {row["email"]: row for row in client.get("/api/admin/users").json()}
    assert rows[address]["last_active_at"] is None
    assert rows[address]["meals"] == 0


def test_users_limit_is_bounded(client, monkeypatch):
    make_admin(client, monkeypatch)
    assert client.get("/api/admin/users", params={"limit": 0}).status_code == 422
    assert client.get("/api/admin/users", params={"limit": 501}).status_code == 422
    assert client.get("/api/admin/users", params={"limit": 1}).status_code == 200


# --- The 0006 fallback -------------------------------------------------------


def test_a_backdated_meal_counts_as_activity_today(client, client_b, monkeypatch):
    """The whole reason meals.created_at exists.

    A meal eaten a week ago but entered now is usage *now*. Keyed off `date`
    alone it would report the user active last week and idle today.
    """
    long_ago = (TODAY - timedelta(days=7)).isoformat()
    client_b.post(
        "/api/meals",
        json={
            "date": long_ago,
            "name": "Backdated",
            "calories": 100,
            "protein": 10,
        },
    )
    make_admin(client, monkeypatch)

    activity = {
        point["date"]: point for point in client.get("/api/admin/stats").json()["activity"]
    }
    assert activity[TODAY.isoformat()]["meals"] == 1
    assert activity[TODAY.isoformat()]["active_users"] == 1
    assert activity[long_ago]["meals"] == 0


def test_a_meal_with_no_created_at_falls_back_to_its_date(client, client_b, monkeypatch):
    """Rows written before migration 0006 have created_at NULL. They must still
    appear, at eat-date precision, rather than disappearing from the totals."""
    client_b.post(
        "/api/meals",
        json={
            "date": YESTERDAY.isoformat(),
            "name": "Legacy",
            "calories": 100,
            "protein": 10,
        },
    )
    with Session(get_engine()) as session:
        meal = session.scalars(select(Meal)).one()
        meal.created_at = None
        session.commit()

    make_admin(client, monkeypatch)
    stats = client.get("/api/admin/stats").json()
    activity = {point["date"]: point for point in stats["activity"]}

    assert stats["total_meals"] == 1
    assert activity[YESTERDAY.isoformat()]["meals"] == 1
    assert activity[TODAY.isoformat()]["meals"] == 0


def test_new_meals_get_a_created_at(client):
    client.post(
        "/api/meals",
        json={
            "date": YESTERDAY.isoformat(),
            "name": "Fresh",
            "calories": 100,
            "protein": 10,
        },
    )
    with Session(get_engine()) as session:
        meal = session.scalars(select(Meal)).one()
        assert meal.created_at is not None
        # Naive UTC, matching every other timestamp in the schema.
        assert meal.created_at.tzinfo is None
        assert abs((utcnow() - meal.created_at).total_seconds()) < 60


# --- Keep-warm panel ---------------------------------------------------------
#
# The panel answers one question -- is the cold start actually being kept away
# -- and every number behind it is in-memory, so the tests below are about the
# logic rather than about durable state. The most important one is the last:
# /api/health must never reach Postgres, because a ping every 10 minutes for 16
# hours a day would hold Neon awake past its free CU-hour allowance and suspend
# the database. See app/keep_warm.py.


def test_keep_warm_reports_the_window_and_a_verdict(client, monkeypatch):
    make_admin(client, monkeypatch)
    body = client.get("/api/admin/keep-warm").json()

    assert body["window_start_hour"] == keep_warm.WINDOW_START_HOUR
    assert body["window_end_hour"] == keep_warm.WINDOW_END_HOUR
    assert body["window_tz"] == keep_warm.WINDOW_TZ
    assert body["spin_down_seconds"] == keep_warm.SPIN_DOWN_S
    assert body["uptime_seconds"] >= 0
    # The process really did just start, so it is either mid-window and cold or
    # outside the window entirely -- never one of the settled states.
    assert body["verdict"] in {"cold", "outside_window"}
    # HH:MM, and the server's own idea of the local clock rather than the
    # test machine's.
    assert len(body["window_local_time"]) == 5
    assert body["window_local_time"][2] == ":"


MARKED_HEALTH = f"/api/health?src={keep_warm.SCHEDULER_MARKER}"


def test_only_marked_requests_count_as_scheduler_pings(client, monkeypatch):
    """The bug this split fixes, asserted directly.

    Render points healthCheckPath at /api/health and hits it about every four
    seconds, so an unmarked request is far more likely to be the platform
    monitor than the scheduler. Production measured 2,714 requests in 3h12m
    where cron-job.org could account for 19. Counting them together made the
    number meaningless and made pings_missing unreachable.
    """
    make_admin(client, monkeypatch)
    keep_warm.mark_boot()

    for _ in range(5):
        assert client.get("/api/health").status_code == 200
    for _ in range(2):
        assert client.get(MARKED_HEALTH).status_code == 200

    body = client.get("/api/admin/keep-warm").json()
    assert body["health_checks"] == 7, "every request counts toward the total"
    assert body["scheduler_pings"] == 2, "only marked ones are scheduler pings"
    assert body["last_scheduler_ping_at"] is not None
    assert body["seconds_since_scheduler_ping"] is not None


def test_an_unrecognised_src_is_not_a_scheduler_ping(client, monkeypatch):
    """A health check must never fail on its query string, so `src` is
    unvalidated -- which means a wrong value has to degrade to "not the
    scheduler" rather than to an error or, worse, to a match."""
    make_admin(client, monkeypatch)
    keep_warm.mark_boot()

    for path in ("/api/health?src=", "/api/health?src=KEEPWARM",
                 "/api/health?src=keepwarm2", "/api/health?other=keepwarm"):
        assert client.get(path).status_code == 200, path

    body = client.get("/api/admin/keep-warm").json()
    assert body["health_checks"] == 4
    assert body["scheduler_pings"] == 0


def test_longest_gap_is_none_until_two_scheduler_pings_have_arrived(
    client, monkeypatch
):
    """None rather than 0. There is no gap before the second ping, and 0 would
    read as "the pings are perfect" rather than "nothing to say yet"."""
    make_admin(client, monkeypatch)
    keep_warm.mark_boot()  # clears the counters, as a real spin-down would

    def longest():
        return client.get("/api/admin/keep-warm").json()[
            "longest_scheduler_gap_seconds"
        ]

    assert longest() is None
    # Unmarked traffic must not open a gap, however much of it there is.
    for _ in range(5):
        client.get("/api/health")
    assert longest() is None
    client.get(MARKED_HEALTH)
    assert longest() is None
    client.get(MARKED_HEALTH)
    assert longest() is not None


def test_window_is_half_open(client):
    """05:00 is inside, 21:00 is outside -- the same boundary keep-warm.yml
    uses, so the panel and the scheduler cannot disagree about an edge hour."""
    def at(hour: int, minute: int = 0) -> bool:
        return keep_warm.in_window_at(datetime(2026, 9, 4, hour, minute))

    assert at(keep_warm.WINDOW_START_HOUR - 1, 59) is False
    assert at(keep_warm.WINDOW_START_HOUR, 0) is True
    assert at(keep_warm.WINDOW_END_HOUR - 1, 59) is True
    assert at(keep_warm.WINDOW_END_HOUR, 0) is False


def test_verdict_reads_uptime_and_scheduler_pings_together():
    """The six states, as a pure function -- no clock, no module state.

    "Up 10 hours at 3 PM proves the pings work; up 40 seconds proves they do
    not" is the whole panel, and this is where that sentence lives in code.
    """
    hour = 60 * 60
    verdict = keep_warm.verdict_for

    # Outside the window the server is *supposed* to be asleep, so nothing
    # about uptime is evidence of anything.
    assert verdict(10 * hour, 60, 60, in_window=False) == "outside_window"
    assert verdict(5, 0, None, in_window=False) == "outside_window"

    # The page load was itself the cold start -- or a deploy just restarted the
    # process, which this cannot see and the copy therefore names too.
    assert verdict(40, 0, None, in_window=True) == "cold"

    # Awake, but not yet past the spin-down interval: nothing is proven either
    # way, and saying so beats guessing.
    assert (
        verdict(keep_warm.COLD_START_SUSPECT_S + 1, 3, 30, in_window=True)
        == "warming"
    )

    # Up long enough to judge, but no marked ping has EVER arrived. Almost
    # always a cron-job.org URL that has not been given ?src=keepwarm yet, so it
    # must not be reported as a scheduler that stopped.
    assert verdict(10 * hour, 0, None, in_window=True) == "awaiting_marked_pings"

    # Marked pings were arriving and then stopped. This is the real alarm, and
    # it is only reachable because Render's own health checks are excluded.
    assert verdict(10 * hour, 40, keep_warm.SPIN_DOWN_S + 1, in_window=True) == (
        "pings_missing"
    )

    # The only state that actually proves the scheduler is landing.
    assert verdict(10 * hour, 40, 4 * 60, in_window=True) == "warm"


def test_health_check_touches_no_database(anon_client):
    """The assertion that protects the entire Neon budget.

    Recording pings in a table is the obvious implementation of this panel, and
    it is the one that takes the database down: /api/health is hit every 10
    minutes across a 16-hour window, which is ~122 CU-hours a month against a
    100 CU-hour free allowance, and Neon suspends the compute until the next
    billing period. A comment saying "don't do that" is not a defence; this is.

    Watches connections as well as statements, because Neon's compute wakes on
    a connection, not on a query.
    """
    engine = get_engine()
    statements: list[str] = []
    connections = 0

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    def on_connect(dbapi_connection, connection_record):
        nonlocal connections
        connections += 1

    event.listen(engine, "before_cursor_execute", on_execute)
    event.listen(engine, "connect", on_connect)
    try:
        assert anon_client.get("/api/health").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
        event.remove(engine, "connect", on_connect)

    assert statements == [], f"/api/health ran SQL: {statements}"
    assert connections == 0, "/api/health opened a database connection"
