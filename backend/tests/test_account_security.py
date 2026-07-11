"""Password change, account deletion, token hardening, and full data export."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import get_jwt_secret
from app.rate_limit import limiter
from tests.conftest import TEST_PASSWORD

NEW_PASSWORD = "new-password-456"


def _me(client):
    return client.get("/api/auth/me").json()


def _token_with_claims(claims: dict) -> str:
    return jwt.encode(claims, get_jwt_secret(), algorithm="HS256")


# --- Token hardening -------------------------------------------------------

def test_tampered_signature_rejected(client):
    user_id = _me(client)["id"]
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=1)},
        "wrong-secret-attacker-controlled",
        algorithm="HS256",
    )
    client.headers["Authorization"] = f"Bearer {forged}"
    assert client.get("/api/meals").status_code == 401


@pytest.mark.parametrize("missing", ["sub", "iat", "exp"])
def test_token_missing_required_claim_rejected(client, missing):
    now = datetime.now(timezone.utc)
    claims = {"sub": "1", "iat": now, "exp": now + timedelta(days=1)}
    del claims[missing]
    client.headers["Authorization"] = f"Bearer {_token_with_claims(claims)}"
    assert client.get("/api/meals").status_code == 401


# --- Change password -------------------------------------------------------

def test_change_password_rejects_wrong_current_password(client):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    # Still logged in; nothing changed.
    assert client.get("/api/meals").status_code == 200


def test_change_password_rejects_short_new_password(client):
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert response.status_code == 422


def test_change_password_rotates_credentials_and_revokes_old_tokens(client):
    user = _me(client)
    now = datetime.now(timezone.utc)
    # Minted well before the change, like a token leaked from another device.
    old_token = _token_with_claims(
        {"sub": str(user["id"]), "iat": now - timedelta(minutes=5),
         "exp": now + timedelta(days=1)}
    )
    assert client.get(
        "/api/meals", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 200

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    fresh_token = response.json()["access_token"]

    # The pre-change token is revoked; the returned one works.
    assert client.get(
        "/api/meals", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401
    assert client.get(
        "/api/meals", headers={"Authorization": f"Bearer {fresh_token}"}
    ).status_code == 200

    # Login now requires the new password.
    email = user["email"]
    assert client.post(
        "/api/auth/login", json={"email": email, "password": TEST_PASSWORD}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": email, "password": NEW_PASSWORD}
    ).status_code == 200


# --- Delete account --------------------------------------------------------

def test_delete_account_rejects_wrong_password(client):
    response = client.request(
        "DELETE", "/api/auth/account", json={"password": "not-my-password"}
    )
    assert response.status_code == 400
    assert client.get("/api/meals").status_code == 200


def test_delete_account_removes_user_and_all_data(client):
    email = _me(client)["email"]
    client.post("/api/meals", json={
        "date": "2026-07-10", "name": "Last supper", "calories": 500, "protein": 30,
    })

    response = client.request(
        "DELETE", "/api/auth/account", json={"password": TEST_PASSWORD}
    )
    assert response.status_code == 204

    # The token is dead and the credentials no longer exist.
    assert client.get("/api/meals").status_code == 401
    assert client.post(
        "/api/auth/login", json={"email": email, "password": TEST_PASSWORD}
    ).status_code == 401
    # The email is free again (data was cascaded away, not orphaned).
    assert client.post(
        "/api/auth/signup", json={"email": email, "password": TEST_PASSWORD}
    ).status_code == 201


def test_delete_account_does_not_touch_other_users(client, client_b):
    client_b.post("/api/meals", json={
        "date": "2026-07-10", "name": "B's meal", "calories": 400, "protein": 25,
    })
    assert client.request(
        "DELETE", "/api/auth/account", json={"password": TEST_PASSWORD}
    ).status_code == 204
    meals = client_b.get("/api/meals", params={"date": "2026-07-10"}).json()
    assert [m["name"] for m in meals] == ["B's meal"]


# --- Full data export ------------------------------------------------------

def test_export_all_includes_every_owned_table(client):
    client.post("/api/meals", json={
        "date": "2026-07-09", "name": "Omelette", "calories": 300, "protein": 20,
    })
    client.post("/api/foods", json={
        "name": "Oats", "serving_size": 40, "calories": 150, "protein": 5,
    })

    body = client.get("/api/data/export/all").json()
    assert body["user"]["email"] == _me(client)["email"]
    assert body["settings"]["calorie_goal"] == 2000
    assert [m["name"] for m in body["meals"]] == ["Omelette"]
    assert [f["name"] for f in body["foods"]] == ["Oats"]
    assert body["ai_analyses"] == []


# --- Rate limiting behind the proxy ----------------------------------------

def test_rate_limit_key_uses_last_forwarded_for_entry(anon_client):
    limiter.reset()
    limiter.enabled = True
    try:
        def attempt(xff):
            return anon_client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "wrong-password"},
                headers={"X-Forwarded-For": xff},
            )

        # Exhaust the limit for the client the proxy reports as 1.1.1.1. The
        # spoofable first entry is ignored, so varying it doesn't help.
        for i in range(10):
            assert attempt(f"9.9.9.{i}, 1.1.1.1").status_code == 401
        assert attempt("8.8.8.8, 1.1.1.1").status_code == 429
        # A different real client is unaffected.
        assert attempt("9.9.9.9, 2.2.2.2").status_code == 401
    finally:
        limiter.enabled = False
        limiter.reset()
