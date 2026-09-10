import logging
import os
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, utcnow
from ..snapshots import ensure_snapshots_quietly
from .security import decode_token

logger = logging.getLogger(__name__)

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
    _mark_seen(db, user)
    return user


def _mark_seen(db: Session, user: User) -> None:
    """Record that this account was here today, at most once per UTC day.

    ⚠️ THIS RUNS ON EVERY AUTHENTICATED REQUEST IN THE APP, which is what
    dictates the shape. The date comparison comes first and is free; on all but
    one request per account per day the function does nothing at all and issues
    no SQL. The user row is already loaded and the session already open, so the
    one day it does write, it costs a single UPDATE on a primary key.

    That bound is the whole argument for the column existing. `admin.py`'s
    `_last_active_by_user` rejected a `last_seen` column because keeping it
    accurate "means a write on every authenticated request" -- true at
    timestamp precision, false at date precision, and nothing reads below the
    day.

    Piggy-backing the daily snapshot here is deliberate: it needs a trigger
    that fires about once a day on a request that has already opened a database
    session, and app/snapshots.py explains at length why neither /api/health
    nor a GitHub Actions cron can be that trigger.

    ⚠️ EVERYTHING HERE IS GUARDED. A failure writing a metric must never fail
    the request that carried it -- an exception raised in this dependency would
    500 the dashboard, the log form and every other authenticated route, for an
    account that merely visited. The rollback is as load-bearing as the except:
    Postgres aborts the whole transaction on error, so leaving it would poison
    the session the handler is about to use.
    """
    today = datetime.now(timezone.utc).date()
    if user.last_seen_at is not None and user.last_seen_at.date() >= today:
        return
    try:
        user.last_seen_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("last_seen_at write failed")
        return
    ensure_snapshots_quietly(db, today)


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
