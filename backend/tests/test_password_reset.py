"""Password reset: enumeration uniformity, token lifecycle, and the Brevo seam.

Brevo is faked at two levels, mirroring test_meal_ai.py. Endpoint tests replace
`email.send_password_reset` and assert on what the router asked for; the service
tests replace httpx.AsyncClient and assert on what email.py actually sends and
how it translates failures. Nothing here touches the network.
"""
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_jwt_secret
from app.db import get_engine
from app.models import PasswordReset, User
from app.rate_limit import limiter
from app.services import email as email_service
from tests.conftest import TEST_PASSWORD

NEW_PASSWORD = "brand-new-password-9"
USER_EMAIL = "reset-me@example.com"


# --- Helpers ---------------------------------------------------------------

def configure_email(monkeypatch):
    """Seam 1: the service function, as the router reaches it.

    Returns the list the fake appends to. The autouse env fixture sets neither
    Brevo variable, so every endpoint test must call this or get a 503.
    """
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "sender@example.com")
    sent: list[dict] = []

    async def record(to_email, reset_url, ttl_minutes):
        sent.append({"to": to_email, "url": reset_url, "ttl": ttl_minutes})

    monkeypatch.setattr(email_service, "send_password_reset", record)
    return sent


def signup(client, email=USER_EMAIL, password=TEST_PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def forgot(client, email=USER_EMAIL, **kwargs):
    return client.post("/api/auth/forgot-password", json={"email": email}, **kwargs)


def reset(client, token, password=NEW_PASSWORD):
    return client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": password}
    )


def login(client, email=USER_EMAIL, password=TEST_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def token_from(sent):
    """The raw token out of the most recent emailed link."""
    return sent[-1]["url"].split("token=")[1]


def rows() -> list[PasswordReset]:
    with Session(get_engine()) as session:
        return list(session.scalars(select(PasswordReset)))


def request_reset(client, monkeypatch, email=USER_EMAIL):
    """Sign up, request a reset, and hand back (sent, raw token)."""
    sent = configure_email(monkeypatch)
    signup(client, email)
    assert forgot(client, email).status_code == 200
    return sent, token_from(sent)


# --- Requesting a link -----------------------------------------------------

def test_forgot_password_emails_a_link_for_a_known_address(anon_client, monkeypatch):
    sent, raw = request_reset(anon_client, monkeypatch)
    assert len(sent) == 1
    assert sent[0]["to"] == USER_EMAIL
    assert sent[0]["url"].startswith(
        "https://macros-calculator-mu.vercel.app/reset-password?token="
    )
    assert sent[0]["ttl"] == 60
    assert len(raw) > 20


def test_the_link_ignores_the_request_host(anon_client, monkeypatch):
    """Host-header injection would poison the link inside the victim's mailbox."""
    sent = configure_email(monkeypatch)
    signup(anon_client)
    response = forgot(
        anon_client,
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )
    assert response.status_code == 200
    assert "evil.example" not in sent[0]["url"]
    assert sent[0]["url"].startswith("https://macros-calculator-mu.vercel.app/")


def test_the_link_uses_the_configured_app_url(anon_client, monkeypatch):
    sent = configure_email(monkeypatch)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173/")
    signup(anon_client)
    forgot(anon_client)
    assert sent[0]["url"].startswith("http://localhost:5173/reset-password?token=")


def test_an_unknown_address_is_answered_identically(anon_client, monkeypatch):
    sent = configure_email(monkeypatch)
    signup(anon_client)
    known = forgot(anon_client)
    unknown = forgot(anon_client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # Only the real account was mailed, and only it has a row.
    assert [s["to"] for s in sent] == [USER_EMAIL]
    assert len(rows()) == 1


def test_the_address_is_normalised_before_lookup(anon_client, monkeypatch):
    sent = configure_email(monkeypatch)
    signup(anon_client, "Foo@Example.com")
    assert forgot(anon_client, "  foo@EXAMPLE.com  ").status_code == 200
    assert sent[0]["to"] == "foo@example.com"


def test_unconfigured_email_is_503_for_every_address(anon_client, monkeypatch):
    configure_email(monkeypatch)
    signup(anon_client)
    monkeypatch.delenv("BREVO_API_KEY")
    known = forgot(anon_client)
    unknown = forgot(anon_client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()
    # The check runs before the lookup, so nothing was recorded either way.
    assert rows() == []


def test_a_missing_sender_address_also_counts_as_unconfigured(
    anon_client, monkeypatch
):
    configure_email(monkeypatch)
    signup(anon_client)
    monkeypatch.delenv("EMAIL_SENDER_ADDRESS")
    assert forgot(anon_client).status_code == 503


# --- What is stored --------------------------------------------------------

def test_the_raw_token_is_never_stored(anon_client, monkeypatch):
    _, raw = request_reset(anon_client, monkeypatch)
    stored = rows()[0].token_hash
    assert stored != raw
    assert stored == hashlib.sha256(raw.encode()).hexdigest()


def test_the_raw_token_never_reaches_the_logs(anon_client, monkeypatch, caplog):
    sent = configure_email(monkeypatch)
    signup(anon_client)
    with caplog.at_level(logging.DEBUG):
        forgot(anon_client)
    assert token_from(sent) not in caplog.text


def test_the_address_never_reaches_the_logs(anon_client, monkeypatch, caplog):
    configure_email(monkeypatch)
    signup(anon_client)
    with caplog.at_level(logging.DEBUG):
        forgot(anon_client)
    assert USER_EMAIL not in caplog.text


# --- Consuming a link ------------------------------------------------------

def test_reset_sets_the_new_password_and_revokes_old_sessions(
    anon_client, monkeypatch
):
    signup(anon_client)
    sent = configure_email(monkeypatch)
    forgot(anon_client)
    user_id = login(anon_client).json()["user"]["id"]

    # A session from five minutes ago, rather than the one signup just handed
    # out. password_changed_at is stored with second precision and JWT `iat` is
    # a whole-second claim, so revocation cannot distinguish tokens minted
    # inside the same second as the reset — an accepted one-second window that
    # change_password depends on to keep its own fresh token alive. Forging the
    # iat tests the revocation rule instead of that boundary.
    now = datetime.now(timezone.utc)
    old_token = jwt.encode(
        {"sub": str(user_id), "iat": now - timedelta(minutes=5),
         "exp": now + timedelta(days=1)},
        get_jwt_secret(), algorithm="HS256",
    )
    assert anon_client.get(
        "/api/meals", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 200

    assert reset(anon_client, token_from(sent)).status_code == 204

    assert anon_client.get(
        "/api/meals", headers={"Authorization": f"Bearer {old_token}"}
    ).status_code == 401
    assert login(anon_client).status_code == 401
    assert login(anon_client, password=NEW_PASSWORD).status_code == 200


def test_a_link_works_only_once(anon_client, monkeypatch):
    _, raw = request_reset(anon_client, monkeypatch)
    assert reset(anon_client, raw).status_code == 204
    second = reset(anon_client, raw, "another-password-7")
    assert second.status_code == 400
    # The first reset stands; the second password was never set.
    assert login(anon_client, password=NEW_PASSWORD).status_code == 200


def test_an_expired_link_is_rejected(anon_client, monkeypatch):
    _, raw = request_reset(anon_client, monkeypatch)
    with Session(get_engine()) as session:
        row = session.scalars(select(PasswordReset)).one()
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=1
        )
        session.commit()
    assert reset(anon_client, raw).status_code == 400
    assert login(anon_client).status_code == 200  # old password still works


def test_unknown_expired_and_used_are_indistinguishable(anon_client, monkeypatch):
    _, raw = request_reset(anon_client, monkeypatch)
    unknown = reset(anon_client, "not-a-real-token")
    assert reset(anon_client, raw).status_code == 204
    used = reset(anon_client, raw)
    assert unknown.status_code == used.status_code == 400
    assert unknown.json() == used.json()


def test_changing_the_password_invalidates_outstanding_links(
    anon_client, monkeypatch
):
    signup_response = signup(anon_client)
    sent = configure_email(monkeypatch)
    forgot(anon_client)
    anon_client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "changed-pw-123"},
        headers={"Authorization": f"Bearer {signup_response.json()['access_token']}"},
    )
    assert reset(anon_client, token_from(sent)).status_code == 400


def test_using_one_link_burns_every_outstanding_link(anon_client, monkeypatch):
    monkeypatch.setattr("app.auth.router.RESEND_COOLDOWN_S", 0)
    sent = configure_email(monkeypatch)
    signup(anon_client)
    forgot(anon_client)
    first = token_from(sent)
    forgot(anon_client)
    second = token_from(sent)
    assert first != second

    assert reset(anon_client, second).status_code == 204
    assert reset(anon_client, first, "yet-another-pw-8").status_code == 400


def test_a_short_password_is_rejected_without_spending_the_link(
    anon_client, monkeypatch
):
    _, raw = request_reset(anon_client, monkeypatch)
    assert reset(anon_client, raw, "short").status_code == 422
    assert reset(anon_client, raw).status_code == 204


def test_deleting_the_account_removes_its_reset_rows(anon_client, monkeypatch):
    signup_response = signup(anon_client)
    configure_email(monkeypatch)
    forgot(anon_client)
    assert len(rows()) == 1
    anon_client.request(
        "DELETE", "/api/auth/account",
        json={"password": TEST_PASSWORD},
        headers={"Authorization": f"Bearer {signup_response.json()['access_token']}"},
    )
    assert rows() == []


# --- Abuse limits, all silent ----------------------------------------------

def test_a_second_request_inside_the_cooldown_sends_nothing(
    anon_client, monkeypatch
):
    sent = configure_email(monkeypatch)
    signup(anon_client)
    first = forgot(anon_client)
    second = forgot(anon_client)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(sent) == 1


def test_the_global_daily_cap_stops_sending_without_showing(
    anon_client, monkeypatch
):
    sent = configure_email(monkeypatch)
    monkeypatch.setenv("PASSWORD_RESET_GLOBAL_DAILY_LIMIT", "1")
    signup(anon_client, "one@example.com")
    signup(anon_client, "two@example.com")
    first = forgot(anon_client, "one@example.com")
    second = forgot(anon_client, "two@example.com")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert [s["to"] for s in sent] == ["one@example.com"]


def test_expired_rows_are_purged_on_any_request(anon_client, monkeypatch):
    configure_email(monkeypatch)
    signup(anon_client)
    with Session(get_engine()) as session:
        user_id = session.scalars(select(User)).one().id
        session.add(
            PasswordReset(
                user_id=user_id,
                token_hash="stale" * 12,
                created_at=datetime(2026, 1, 1),
                expires_at=datetime(2026, 1, 1),
            )
        )
        session.commit()
    # An address with no account: the purge still has to run.
    forgot(anon_client, "nobody@example.com")
    assert rows() == []


# --- Access and isolation --------------------------------------------------

def test_both_endpoints_are_public(anon_client, monkeypatch):
    """Guards against anyone adding get_current_user to these routes."""
    configure_email(monkeypatch)
    assert forgot(anon_client, "nobody@example.com").status_code == 200
    assert reset(anon_client, "not-a-real-token").status_code == 400


def test_a_stale_session_does_not_affect_someone_elses_reset(
    client, anon_client, monkeypatch
):
    """The frontend attaches its bearer token with no opt-out; it must be ignored."""
    sent = configure_email(monkeypatch)
    signup(anon_client, "victim@example.com")
    forgot(anon_client, "victim@example.com")

    # `client` is signed in as a different user and keeps its Authorization header.
    assert reset(client, token_from(sent)).status_code == 204
    assert client.get("/api/auth/me").status_code == 200  # A's session untouched
    assert login(anon_client, "victim@example.com", NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "call, limit, expected",
    [
        (lambda c: forgot(c, "nobody@example.com"), 5, 200),
        (lambda c: reset(c, "not-a-real-token"), 10, 400),
    ],
)
def test_the_reset_endpoints_are_rate_limited_per_ip(
    anon_client, monkeypatch, call, limit, expected
):
    configure_email(monkeypatch)
    limiter.reset()
    limiter.enabled = True
    try:
        attempts = [call(anon_client) for _ in range(limit + 1)]
        assert all(r.status_code == expected for r in attempts[:limit])
        assert attempts[limit].status_code == 429
    finally:
        limiter.enabled = False
        limiter.reset()


def test_a_failing_provider_still_answers_200(anon_client, monkeypatch, caplog):
    """The cost of sending in the background: only the log knows it failed."""
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "sender@example.com")

    async def boom(*_args, **_kwargs):
        raise email_service.EmailUnavailable("brevo is down")

    monkeypatch.setattr(email_service, "send_password_reset", boom)
    signup(anon_client)
    with caplog.at_level(logging.ERROR):
        response = forgot(anon_client)
    assert response.status_code == 200
    assert "Password reset email failed" in caplog.text


# --- Seam 2: what email.py actually sends ----------------------------------

def _install_fake_brevo(monkeypatch, *, status=201, exc=None, capture=None):
    """Replace httpx.AsyncClient so email.py's own translation is exercised.

    Returns real httpx.Response objects so raise_for_status behaves exactly as
    it does in production.
    """
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "sender@example.com")

    class FakeClient:
        def __init__(self, **kwargs):
            if capture is not None:
                capture["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            if capture is not None:
                capture["url"] = url
                capture.update(kwargs)
            if exc is not None:
                raise exc
            return httpx.Response(
                status,
                request=httpx.Request("POST", url),
                json={"messageId": "<abc@brevo>"},
            )

    monkeypatch.setattr(email_service.httpx, "AsyncClient", FakeClient)


def test_a_successful_send_posts_to_brevo(monkeypatch):
    capture: dict = {}
    _install_fake_brevo(monkeypatch, capture=capture)
    asyncio.run(
        email_service.send_password_reset(
            "someone@example.com",
            "https://app.example/reset-password?token=abc",
            60,
        )
    )
    assert capture["url"] == email_service.BREVO_API_URL
    assert capture["headers"]["api-key"] == "test-key"
    # An explicit timeout: httpx has none by default, and an unanswered
    # connection would pin a worker on the free instance.
    assert capture["client_kwargs"]["timeout"] == email_service.SEND_TIMEOUT_S

    payload = capture["json"]
    assert payload["to"] == [{"email": "someone@example.com"}]
    assert payload["sender"]["email"] == "sender@example.com"
    assert payload["sender"]["name"] == "Macros Calculator"
    # Both parts, both carrying the link and the real expiry.
    for part in (payload["textContent"], payload["htmlContent"]):
        assert "https://app.example/reset-password?token=abc" in part
        assert "60 minutes" in part
        assert "Macros Calculator" in part


def test_the_sender_name_is_configurable(monkeypatch):
    capture: dict = {}
    _install_fake_brevo(monkeypatch, capture=capture)
    monkeypatch.setenv("EMAIL_SENDER_NAME", "My Tracker")
    asyncio.run(email_service.send_password_reset("a@b.com", "https://x/y", 30))
    assert capture["json"]["sender"]["name"] == "My Tracker"


@pytest.mark.parametrize(
    "status, expected",
    [
        (429, email_service.EmailRateLimited),
        (500, email_service.EmailUnavailable),
        (503, email_service.EmailUnavailable),
        (400, email_service.EmailBadRequest),
        (401, email_service.EmailBadRequest),
    ],
)
def test_provider_statuses_map_to_neutral_errors(monkeypatch, status, expected):
    _install_fake_brevo(monkeypatch, status=status)
    with pytest.raises(expected):
        asyncio.run(email_service.send_password_reset("a@b.com", "https://x/y", 60))


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("no route"),
        httpx.ReadTimeout("too slow"),
        OSError("socket closed"),
    ],
)
def test_transport_failures_map_to_unreachable(monkeypatch, exc):
    _install_fake_brevo(monkeypatch, exc=exc)
    with pytest.raises(email_service.EmailUnreachable):
        asyncio.run(email_service.send_password_reset("a@b.com", "https://x/y", 60))


def test_unexpected_errors_map_to_internal_error(monkeypatch):
    _install_fake_brevo(monkeypatch, exc=RuntimeError("something else"))
    with pytest.raises(email_service.EmailInternalError):
        asyncio.run(email_service.send_password_reset("a@b.com", "https://x/y", 60))


def test_is_configured_needs_both_key_and_sender(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_SENDER_ADDRESS", raising=False)
    assert email_service.is_configured() is False
    monkeypatch.setenv("BREVO_API_KEY", "k")
    assert email_service.is_configured() is False
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "s@e.com")
    assert email_service.is_configured() is True
    # Values pasted into a dashboard often arrive quoted or newline-padded.
    monkeypatch.setenv("BREVO_API_KEY", ' "k"\n')
    assert email_service.is_configured() is True
