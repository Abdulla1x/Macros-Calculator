"""Numeric env settings, and the requests they used to take down.

These call the readers directly rather than through a request wherever the bug
is in reading the value -- a full round trip would only add ways for the test to
fail for unrelated reasons. The exceptions are the login and signup cases, which
exist precisely to prove the request survives, and so have to be requests.
"""
import math

import pytest

from app.auth import security
from app.auth.security import DEFAULT_TOKEN_DAYS, TOKEN_DAYS_ENV, token_lifetime
from app.env import env_float, env_int
from app.services import meal_ai

# "2O" is the letter O. "²" is the superscript two, which .isdigit() accepts and
# int() then raises on -- the exact input that made the old guard worse than
# useless, since it passed the check and crashed on the conversion.
UNREADABLE = ("2O", "abc", "20 30", "twenty", "", "   ", "٢²", "1,000")


@pytest.mark.parametrize("raw", UNREADABLE)
def test_env_int_falls_back_when_the_value_is_unreadable(monkeypatch, raw):
    monkeypatch.setenv("SOME_LIMIT", raw)
    assert env_int("SOME_LIMIT", 20) == 20


def test_env_int_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_LIMIT", raising=False)
    assert env_int("SOME_LIMIT", 20) == 20


def test_env_int_honours_a_deliberate_zero(monkeypatch):
    """0 is a kill switch, not a mistake. Substituting the default would be the
    opposite of what the operator asked for."""
    monkeypatch.setenv("SOME_LIMIT", "0")
    assert env_int("SOME_LIMIT", 20) == 0


def test_env_int_clamps_a_negative_to_zero(monkeypatch):
    """A negative already blocked everything. Falling back to the shipped
    default would take a setting that was closing a gate and reopen it."""
    monkeypatch.setenv("SOME_LIMIT", "-5")
    assert env_int("SOME_LIMIT", 20) == 0


@pytest.mark.parametrize("raw,expected", [("30", 30), ("  30  ", 30), ('"30"', 30), ("'30'", 30)])
def test_env_int_reads_a_valid_value_through_dashboard_mangling(monkeypatch, raw, expected):
    monkeypatch.setenv("SOME_LIMIT", raw)
    assert env_int("SOME_LIMIT", 20) == expected


@pytest.mark.parametrize("raw", UNREADABLE)
def test_env_float_falls_back_when_the_value_is_unreadable(monkeypatch, raw):
    monkeypatch.setenv("SOME_SECONDS", raw)
    assert env_float("SOME_SECONDS", 60.0) == 60.0


@pytest.mark.parametrize("raw", ["inf", "-inf", "Infinity", "nan", "NaN"])
def test_env_float_rejects_non_finite_values(monkeypatch, raw):
    """float() accepts all of these. timedelta(days=inf) then raises
    OverflowError, which would reinstate the 500 one layer further away."""
    monkeypatch.setenv("SOME_SECONDS", raw)
    assert env_float("SOME_SECONDS", 60.0) == 60.0


@pytest.mark.parametrize("raw,expected", [("1.5", 1.5), ("90", 90.0), ('"1e2"', 100.0), ("-3", -3.0)])
def test_env_float_reads_a_valid_value(monkeypatch, raw, expected):
    """Including the negative: env_float does not clamp, because what a
    non-positive duration means is the caller's decision, not the parser's."""
    monkeypatch.setenv("SOME_SECONDS", raw)
    assert env_float("SOME_SECONDS", 60.0) == expected


# --- ACCESS_TOKEN_DAYS -------------------------------------------------------
#
# The setting is absent from render.yaml, so the dashboard is the only place it
# can be set and the only place a typo can come from. It is read inside
# create_access_token, which login and signup call and nothing else does.


@pytest.mark.parametrize("raw", ["7d", "seven", "", "inf", "nan", "0", "-1"])
def test_token_lifetime_falls_back_to_the_shipped_default(monkeypatch, raw):
    monkeypatch.setenv(TOKEN_DAYS_ENV, raw)
    assert token_lifetime().days == DEFAULT_TOKEN_DAYS


def test_token_lifetime_reads_a_valid_fractional_value(monkeypatch):
    """Fractions are why this is a float at all -- a short-lived token for a
    test deployment is a legitimate thing to want."""
    monkeypatch.setenv(TOKEN_DAYS_ENV, "0.5")
    assert token_lifetime().total_seconds() == 12 * 60 * 60


@pytest.mark.parametrize("raw", ["7d", "inf", "0", "-1"])
def test_login_and_signup_survive_a_malformed_token_lifetime(anon_client, monkeypatch, raw):
    """The bug this fixes, at the level the user met it.

    A bare float() raised inside create_access_token, so the only two ways into
    the app 500'd for everyone while /api/health went on answering 200.
    """
    monkeypatch.setenv(TOKEN_DAYS_ENV, raw)

    signup = anon_client.post(
        "/api/auth/signup", json={"email": "typo@example.com", "password": "test-password-123"}
    )
    assert signup.status_code == 201, signup.text

    login = anon_client.post(
        "/api/auth/login", json={"email": "typo@example.com", "password": "test-password-123"}
    )
    assert login.status_code == 200, login.text

    # The token has to actually work. "0" and "-1" never raised -- they minted a
    # token that had already expired, so login answered 200 and the very next
    # request answered 401. A status code alone cannot tell that from success.
    token = login.json()["access_token"]
    authed = anon_client.get("/api/settings", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200, authed.text


def test_a_malformed_token_lifetime_is_reported_at_startup(monkeypatch, caplog):
    """Logged next to the deploy that caused it, not on a user's login later."""
    monkeypatch.setenv(TOKEN_DAYS_ENV, "7d")
    with caplog.at_level("WARNING", logger=security.__name__):
        token_lifetime()
    assert TOKEN_DAYS_ENV in caplog.text


# --- MEAL_AI_DEADLINE_S ------------------------------------------------------


@pytest.mark.parametrize("raw", ["²", "60s", "abc", "0", "-1"])
def test_deadline_falls_back_on_junk(monkeypatch, raw):
    """The old guard was raw.replace(".", "", 1).isdigit() -- a hand-rolled
    float parser that accepted "²" and then raised inside float(), on every
    analyze and every transcribe."""
    monkeypatch.setenv("MEAL_AI_DEADLINE_S", raw)
    assert meal_ai._deadline(60.0) == 60.0


@pytest.mark.parametrize("raw,expected", [("90", 90.0), ("1.5", 1.5), ('"45"', 45.0), ("1e2", 100.0)])
def test_deadline_reads_a_valid_value(monkeypatch, raw, expected):
    """1e2 is the case the old guard rejected: a legitimate float spelling that
    .isdigit() has no idea what to do with."""
    monkeypatch.setenv("MEAL_AI_DEADLINE_S", raw)
    assert meal_ai._deadline(60.0) == expected


def test_non_finite_deadline_cannot_produce_an_infinite_retry_budget(monkeypatch):
    monkeypatch.setenv("MEAL_AI_DEADLINE_S", "inf")
    value = meal_ai._deadline(60.0)
    assert math.isfinite(value) and value == 60.0
