from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import get_jwt_secret
from app.rate_limit import limiter
from tests.conftest import TEST_PASSWORD


def signup(client, email, password=TEST_PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def login(client, email, password=TEST_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signup_returns_token_and_creates_settings(anon_client):
    response = signup(anon_client, "new@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "new@example.com"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert anon_client.get("/api/auth/me", headers=headers).json() == body["user"]
    # A default settings row exists from the moment of signup.
    settings = anon_client.get("/api/settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["calorie_goal"] == 2000


def test_signup_normalizes_and_rejects_duplicate_email_case_insensitively(anon_client):
    assert signup(anon_client, "Foo@Example.com").status_code == 201
    assert signup(anon_client, "foo@example.com").status_code == 409
    assert signup(anon_client, "FOO@EXAMPLE.COM").status_code == 409
    # Stored lowercase; login works regardless of case.
    assert login(anon_client, "fOo@eXample.com").status_code == 200


def test_signup_rejects_short_password_and_bad_email(anon_client):
    assert signup(anon_client, "a@b.com", "short").status_code == 422
    assert signup(anon_client, "not-an-email").status_code == 422


def test_login_wrong_password_and_unknown_email_are_identical(anon_client):
    signup(anon_client, "known@example.com")
    wrong_pw = login(anon_client, "known@example.com", "wrong-password-1")
    unknown = login(anon_client, "unknown@example.com")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()


def test_login_is_rate_limited_per_ip(anon_client):
    signup(anon_client, "ratelimited@example.com")
    limiter.reset()
    limiter.enabled = True
    try:
        attempts = [
            login(anon_client, "ratelimited@example.com", "wrong-password-1")
            for _ in range(11)
        ]
        assert all(r.status_code == 401 for r in attempts[:10])
        assert attempts[10].status_code == 429
        assert "Too many attempts" in attempts[10].json()["detail"]
        # The right password is also throttled — the limit is per IP, not per outcome.
        assert login(anon_client, "ratelimited@example.com").status_code == 429
    finally:
        limiter.enabled = False
        limiter.reset()


def test_garbage_token_rejected(client):
    client.headers["Authorization"] = "Bearer not.a.token"
    assert client.get("/api/meals").status_code == 401


def test_expired_token_rejected(client):
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": "1", "iat": now - timedelta(days=8), "exp": now - timedelta(days=1)},
        get_jwt_secret(),
        algorithm="HS256",
    )
    client.headers["Authorization"] = f"Bearer {expired}"
    assert client.get("/api/meals").status_code == 401


def test_token_for_deleted_user_rejected(anon_client):
    # A structurally valid token whose subject doesn't exist.
    ghost = jwt.encode(
        {
            "sub": "99999",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        get_jwt_secret(),
        algorithm="HS256",
    )
    response = anon_client.get("/api/meals", headers={"Authorization": f"Bearer {ghost}"})
    assert response.status_code == 401


# Every data endpoint must reject unauthenticated requests.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/meals"),
    ("POST", "/api/meals"),
    ("PUT", "/api/meals/1"),
    ("DELETE", "/api/meals/1"),
    ("GET", "/api/foods"),
    ("GET", "/api/foods/search?q=a"),
    ("GET", "/api/foods/lookup?q=a"),
    ("POST", "/api/foods"),
    ("DELETE", "/api/foods/1"),
    ("GET", "/api/analytics/daily"),
    ("GET", "/api/settings"),
    ("PUT", "/api/settings"),
    ("GET", "/api/data/export"),
    ("GET", "/api/data/export/all"),
    ("POST", "/api/data/import"),
    ("POST", "/api/auth/change-password"),
    ("DELETE", "/api/auth/account"),
    ("POST", "/api/ai/analyze"),
    ("PATCH", "/api/ai/analyses/1"),
    ("GET", "/api/auth/me"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
def test_endpoints_require_auth(anon_client, method, path):
    response = anon_client.request(method, path)
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_health_stays_public(anon_client):
    assert anon_client.get("/api/health").status_code == 200
