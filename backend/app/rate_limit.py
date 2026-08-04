"""Per-client rate limiting (in-memory — fine on a single instance).

Only the auth endpoints are limited: everything else already requires a valid
token, while these are reachable by anyone. Login and signup are the
brute-force surface; the password-reset pair is the abuse surface, since one of
them sends mail to a third party at our expense.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Real client IP behind the reverse proxy (Render).

    In production `request.client.host` is the proxy's address, which would
    collapse every user into one shared rate-limit bucket. The proxy appends
    the true client IP as the *last* entry of X-Forwarded-For; earlier entries
    are client-supplied and spoofable, so only the last one is trusted.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        ip = forwarded.rsplit(",", 1)[-1].strip()
        if ip:
            return ip
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)

LOGIN_LIMIT = "10/minute"
SIGNUP_LIMIT = "5/minute"
# change-password / delete-account verify a password, so they get the same
# brute-force protection as login.
ACCOUNT_LIMIT = "10/minute"
# Far tighter than signup, and per hour rather than per minute: this is the one
# endpoint that spends a finite third-party quota and puts mail in someone
# else's inbox. Nobody legitimately forgets their password five times an hour.
FORGOT_PASSWORD_LIMIT = "5/hour"
# Abuse control only. Guessing a 256-bit token is not a threat model, so this
# exists to stop someone hammering the endpoint, not to protect the token.
RESET_PASSWORD_LIMIT = "10/hour"
