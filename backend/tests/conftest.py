import itertools
import json
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import dispose_engine
from app.main import app
from app.rate_limit import limiter

TEST_PASSWORD = "test-password-123"

_user_counter = itertools.count(1)


def utc_today() -> date:
    """Today by the UTC clock -- the day boundary the *counters* bucket on.

    This app has two day notions and they are not interchangeable:

    * **Counters** bucket by UTC, because they count `created_at` timestamps,
      which are stored naive UTC (`routers/admin.py`, `calls_today` in
      `routers/ai.py`, the reset quota in `auth/router.py`).
    * **User-facing dates** -- a meal's date, a water log's day -- use the
      server's *local* date via `date_type.today()`, because they are calendar
      dates the client sends.

    On Render both are UTC, so the two coincide in production and no test ever
    noticed. On a developer's machine east of UTC they diverge for the first
    hours of the morning, and a test that indexes a UTC-bucketed series with
    `date.today()` fails at 02:00 for reasons unrelated to the code.

    Use this only where the code under test buckets by UTC. Everywhere else
    `date.today()` is correct, because it is what the server itself will use.
    """
    return datetime.now(timezone.utc).date()


def post_raw_json(client, path, body):
    """POST a body httpx would refuse to serialize, e.g. one containing `inf`.

    httpx rejects non-finite floats outright ("Out of range float values are not
    JSON compliant"), so `json=` cannot express the request this is testing.
    Python's json.dumps writes the bare token `Infinity` and json.loads accepts
    it, which is exactly why the input is reachable from any hand-written client
    and worth a test at all. Serializing here and sending the result as raw
    content is the only way to reproduce it.
    """
    return client.post(
        path, content=json.dumps(body), headers={"Content-Type": "application/json"}
    )


def put_raw_json(client, path, body):
    """PUT counterpart of post_raw_json."""
    return client.put(
        path, content=json.dumps(body), headers={"Content-Type": "application/json"}
    )


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
    # Cleared, not defaulted: ADMIN_EMAILS is read from the real environment, so
    # a developer who has it exported would otherwise run a different suite than
    # CI does — and the difference would be "admin routes are open".
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    # All TestClient requests share one fake IP, so the per-IP auth rate limit
    # would trip across tests. Tests that exercise it re-enable it explicitly.
    limiter.enabled = False
    dispose_engine()
    yield
    dispose_engine()


@pytest.fixture
def make_authed_client():
    """Factory: each call signs up a fresh user and returns a client for them."""
    clients: list[TestClient] = []

    def _make() -> TestClient:
        test_client = TestClient(app)
        test_client.__enter__()
        clients.append(test_client)
        email = f"user{next(_user_counter)}@example.com"
        response = test_client.post(
            "/api/auth/signup", json={"email": email, "password": TEST_PASSWORD}
        )
        assert response.status_code == 201, response.text
        token = response.json()["access_token"]
        test_client.headers["Authorization"] = f"Bearer {token}"
        return test_client

    yield _make
    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture
def client(make_authed_client):
    return make_authed_client()


@pytest.fixture
def client_b(make_authed_client):
    return make_authed_client()


@pytest.fixture
def anon_client():
    with TestClient(app) as test_client:
        yield test_client
