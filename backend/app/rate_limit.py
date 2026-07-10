"""Per-IP rate limiting (in-memory — fine on a single instance).

Only the auth endpoints are limited: everything else already requires a valid
token, but login/signup are the brute-force surface.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

LOGIN_LIMIT = "10/minute"
SIGNUP_LIMIT = "5/minute"
