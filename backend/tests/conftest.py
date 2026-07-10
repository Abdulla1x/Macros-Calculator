import itertools

import pytest
from fastapi.testclient import TestClient

from app.db import dispose_engine
from app.main import app
from app.rate_limit import limiter

TEST_PASSWORD = "test-password-123"

_user_counter = itertools.count(1)


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("JWT_SECRET", "test-secret-0123456789abcdef0123456789abcdef")
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
