import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)

# Admins are named in an env var, not a database column. That is a deliberate
# tradeoff: with no `role` column there is no promotion endpoint, and with no
# promotion endpoint there is no privilege-escalation surface to defend. It also
# means the permission itself needs no migration.
ADMIN_EMAILS_ENV = "ADMIN_EMAILS"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id, issued_at = decode_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized()
    # Changing the password revokes every token issued before the change.
    if user.password_changed_at is not None and issued_at < user.password_changed_at:
        raise _unauthorized()
    return user


def admin_emails() -> set[str]:
    """The admin allowlist, lowercased, read fresh on every call.

    Read at call time rather than import time for two reasons. render.yaml is
    not synced to the Render dashboard, so this value is edited there and can
    change under a running process. And the tests cannot know their user's
    address until after the app has booted -- conftest numbers users from a
    session-wide counter -- so they set the var mid-test. `status_banner` reads
    STATUS_BANNER the same way, for the same reason.

    Unset or empty means *nobody* is an admin. That is the only safe default:
    the value is not committed anywhere, so a deploy that forgets it has to
    lock everyone out rather than let everyone in.
    """
    # .strip('"').strip("'") mirrors the _env() helper in services/email.py. A
    # value pasted into the Render dashboard with surrounding quotes is a real
    # failure mode this project has already hit, and it fails silently -- the
    # address simply never matches and the route just 403s forever.
    raw = os.environ.get(ADMIN_EMAILS_ENV, "").strip().strip('"').strip("'")
    # The trailing `if part.strip()` drops empty segments, so "a,,b" and a
    # trailing comma both parse cleanly. Same shape as the CORS_ORIGINS split
    # in main.py.
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_admin(user: User) -> bool:
    """Whether this user is on the allowlist.

    Signup stores emails lowercased (auth/router.py normalises with
    `.strip().lower()`), so lowercasing both sides is what lets an address
    typed into the dashboard in any case still match the stored row.
    """
    return user.email.strip().lower() in admin_emails()


def require_admin(user: User = Depends(get_current_user)) -> User:
    """`get_current_user`, plus an allowlist check. Returns the same User.

    403 rather than 404. Hiding the route's existence would buy nothing -- the
    frontend bundle names /api/admin either way -- and a 404 would make a
    misconfigured ADMIN_EMAILS indistinguishable from a broken deploy, which is
    the last confusion you want while debugging your own access.
    """
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
