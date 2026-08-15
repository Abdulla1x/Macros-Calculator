"""Admin metrics: who may read them, and what they must never contain."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Meal, utcnow

ADMIN_ROUTES = ("/api/admin/stats", "/api/admin/users")

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)

# Deliberately distinctive so the privacy test can grep whole payloads for them
# rather than asserting the absence of a field name it has to know in advance.
SECRET_MEAL_NAME = "Zzyzx Clandestine Casserole"
SECRET_WEIGHT_KG = 83.7
SECRET_TEMPLATE_NAME = "Quixotic Ptarmigan Breakfast"
SECRET_INGREDIENT_NAME = "Vermillion Sprocket Oats"


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

    make_admin(client, monkeypatch)
    for route in ADMIN_ROUTES:
        body = client.get(route).text
        assert SECRET_MEAL_NAME not in body, route
        assert str(SECRET_WEIGHT_KG) not in body, route
        assert SECRET_TEMPLATE_NAME not in body, route
        assert SECRET_INGREDIENT_NAME not in body, route


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
