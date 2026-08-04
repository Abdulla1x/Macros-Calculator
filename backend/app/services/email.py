"""Transactional email via Brevo.

This is the ONLY Brevo-aware module: callers depend on the provider-neutral
EmailError hierarchy below, so switching providers later means rewriting this
file and changing env vars, nothing else.

Brevo was chosen over Resend because it is the only free tier that will mail
*arbitrary* recipients from a single verified sender address with no domain of
our own — Resend without a verified domain can only send from onboarding@
resend.dev, in practice only back to your own address. The cost of that choice:
since the Gmail/Yahoo sender rules of Feb 2024, Brevo rewrites the From domain
to @brevosend.com whenever the sending domain isn't authenticated, and a free
provider domain (gmail.com and friends) cannot be authenticated at all. Mail
still delivers — Brevo's own DKIM signs it — but the recipient sees an
unfamiliar "via brevosend.com" sender, which is why the copy below leads with
the app's name. Authenticating a real domain later changes EMAIL_SENDER_ADDRESS
and nothing in this file.
"""
import logging
import os
import ssl
from contextlib import contextmanager
from html import escape

import httpx

logger = logging.getLogger(__name__)

API_KEY_ENV = "BREVO_API_KEY"
SENDER_EMAIL_ENV = "EMAIL_SENDER_ADDRESS"
SENDER_NAME_ENV = "EMAIL_SENDER_NAME"
# What the recipient sees as the display name. The address beside it is likely
# to be rewritten (see the module docstring), so this name is doing real work.
DEFAULT_SENDER_NAME = "Macros Calculator"

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# Without an explicit timeout httpx waits forever, which on a single free
# instance means one unanswered connection pins a worker until the platform
# kills it. Ten seconds is generous for a JSON POST that normally answers in
# well under one — and this call runs in a background task, so the user is not
# waiting on it either way.
SEND_TIMEOUT_S = 10.0


class EmailError(Exception):
    """Base for provider failures, so callers never import provider symbols."""


class EmailRateLimited(EmailError):
    """Provider quota or per-minute rate limit exhausted.

    On the free tier this is the 300-emails-a-day ceiling, which is shared with
    marketing sends — so it can be exhausted by something that isn't this app.
    """


class EmailUnavailable(EmailError):
    """Provider answered with an HTTP 5xx — its outage, and waiting fixes it."""


class EmailUnreachable(EmailError):
    """No answer at all: DNS, TCP, TLS, or our own timeout expired.

    Split from EmailUnavailable for the same reason meal_ai splits them: a 5xx
    is Brevo's problem, this one is our network or a timeout we set too tight,
    and folding them together turns a log line into a guess.
    """


class EmailBadRequest(EmailError):
    """Provider rejected the request: bad key, unverified sender, bad payload.

    Retrying won't help. The likeliest cause by far is EMAIL_SENDER_ADDRESS
    naming an address that was never verified in the Brevo dashboard, which
    Brevo refuses with a 400.
    """


class EmailInternalError(EmailError):
    """Our own plumbing raised something we don't recognise."""


# Note there is deliberately no EmailBadResponse, unlike meal_ai. There the
# provider's reply had to parse into a MealAnalysis and could arrive unusable;
# here a 2xx *is* the entire success signal and the body is discarded, so there
# is no third state to name.


def _env(name: str) -> str:
    """Read an env var, tolerating how dashboards mangle pasted values.

    A key with a trailing newline or wrapping quotes is rejected as
    unauthorised — indistinguishable from a revoked key, and invisible in a
    dashboard's masked field. Same helper as meal_ai's; duplicated rather than
    shared because the point of a provider module is that it stands alone.
    """
    return os.environ.get(name, "").strip().strip('"').strip("'").strip()


def is_configured() -> bool:
    """Both halves are required: a key with no verified sender cannot send."""
    return bool(_env(API_KEY_ENV) and _env(SENDER_EMAIL_ENV))


@contextmanager
def _provider_errors():
    """Translate provider exceptions into the neutral hierarchy, logging why.

    This is the only place Brevo's own words are recorded — callers get an
    EmailError with no httpx types attached, so the router stays
    provider-agnostic. The log prefixes are deliberately distinct and greppable
    ("Brevo rejected", "Brevo server error", "Brevo unreachable"): a send
    happens in a background task after the response has gone out, so these lines
    are the *only* record that a reset email failed.
    """
    try:
        yield
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        # Brevo's error body names the actual problem (unverified sender,
        # invalid key, quota) and contains nothing of ours. Truncated because an
        # HTML error page from a proxy would otherwise flood the log.
        detail = exc.response.text[:300]
        if status == 429:
            logger.error("Brevo rate limited the send (code=%s): %s", status, detail)
            raise EmailRateLimited(detail) from exc
        if status >= 500:
            logger.error("Brevo server error (code=%s): %s", status, detail)
            raise EmailUnavailable(detail) from exc
        logger.error("Brevo rejected the request (code=%s): %s", status, detail)
        raise EmailBadRequest(detail) from exc
    except (httpx.TransportError, ssl.SSLError, OSError) as exc:
        # Never got a reply. httpx.TransportError covers ConnectError,
        # ReadTimeout and the rest of that family in one line — including our
        # own SEND_TIMEOUT_S expiring — and OSError catches the socket-level
        # failures httpx doesn't wrap.
        logger.error("Brevo unreachable (kind=%s): %s", type(exc).__name__, exc)
        raise EmailUnreachable(f"{type(exc).__name__}: {exc}") from exc
    except EmailError:
        raise
    except Exception as exc:
        logger.exception(
            "Brevo call raised an unexpected error (kind=%s)", type(exc).__name__
        )
        raise EmailInternalError(f"{type(exc).__name__}: {exc}") from exc


def _password_reset_body(reset_url: str, ttl_minutes: int) -> tuple[str, str]:
    """The reset email, as (text, html).

    Content lives with the provider call for the same reason meal_ai owns its
    SYSTEM_PROMPT: it is the payload, and splitting payload from the call that
    sends it is how the two drift.

    Both parts are sent. A text/plain alternative is not decoration here — an
    HTML-only message from an unauthenticated sender is a recognised spam
    signal, and this sender is already starting from behind.

    The app's name leads because the From line probably won't carry it (see the
    module docstring), and "reset your password" from an unrecognised address is
    exactly the shape of a phishing mail. The lifetime is interpolated from the
    caller's value so the copy cannot drift from the token's real expiry.
    """
    text = (
        f"Macros Calculator — password reset\n\n"
        f"Someone asked to reset the password for this email address. Open the "
        f"link below to choose a new one:\n\n"
        f"{reset_url}\n\n"
        f"The link works for {ttl_minutes} minutes and can only be used once.\n\n"
        f"If you didn't ask for this, you can ignore this email — your password "
        f"stays as it is.\n"
    )
    safe_url = escape(reset_url, quote=True)
    html = (
        f'<div style="font-family:system-ui,sans-serif;line-height:1.5">'
        f"<h2>Macros Calculator — password reset</h2>"
        f"<p>Someone asked to reset the password for this email address. "
        f"Choose a new one here:</p>"
        f'<p><a href="{safe_url}">Reset your password</a></p>'
        f"<p>The link works for {ttl_minutes} minutes and can only be used "
        f"once.</p>"
        f"<p>If you didn't ask for this, you can ignore this email — your "
        f"password stays as it is.</p>"
        f'<p style="color:#64748b;font-size:12px">If the link doesn\'t open, '
        f"copy and paste this into your browser:<br>{safe_url}</p>"
        f"</div>"
    )
    return text, html


async def send_password_reset(
    to_email: str, reset_url: str, ttl_minutes: int
) -> None:
    """Send one password-reset email, or raise an EmailError.

    A fresh client per call rather than a module-level pooled one: this endpoint
    sends a handful of messages a day, so there is no pool to be worth keeping
    warm, and a long-lived client would need wiring into the app lifespan to be
    closed properly.
    """
    text, html = _password_reset_body(reset_url, ttl_minutes)
    payload = {
        "sender": {
            "email": _env(SENDER_EMAIL_ENV),
            "name": _env(SENDER_NAME_ENV) or DEFAULT_SENDER_NAME,
        },
        "to": [{"email": to_email}],
        "subject": "Reset your Macros Calculator password",
        "textContent": text,
        "htmlContent": html,
    }
    with _provider_errors():
        async with httpx.AsyncClient(timeout=SEND_TIMEOUT_S) as client:
            response = await client.post(
                BREVO_API_URL,
                headers={
                    "api-key": _env(API_KEY_ENV),
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=payload,
            )
            # Brevo answers a successful send with 201, not 200 — never assert
            # on 200 anywhere. raise_for_status covers both.
            response.raise_for_status()
