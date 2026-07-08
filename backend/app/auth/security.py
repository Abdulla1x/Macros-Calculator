"""Password hashing (Argon2) and JWT access tokens."""
import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from ..db import get_database_url

ALGORITHM = "HS256"
# Only ever used against a local SQLite database; non-SQLite refuses to start
# without a real JWT_SECRET (enforced in main.py's lifespan).
_DEV_SECRET = "dev-only-secret-not-for-production"

_password_hash = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    if get_database_url().startswith("sqlite"):
        return _DEV_SECRET
    raise RuntimeError(
        "JWT_SECRET must be set when running against a non-SQLite database."
    )


def _token_lifetime() -> timedelta:
    return timedelta(days=float(os.environ.get("ACCESS_TOKEN_DAYS", "7")))


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),  # PyJWT requires a string subject
        "iat": now,
        "exp": now + _token_lifetime(),
    }
    return jwt.encode(claims, get_jwt_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    """Returns the user id, or raises jwt.InvalidTokenError."""
    claims = jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    try:
        return int(claims["sub"])
    except (TypeError, ValueError):
        raise jwt.InvalidTokenError("Malformed subject claim")
