import hashlib
import logging
import os
import secrets
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PasswordReset, Setting, User, utcnow
from ..rate_limit import (
    ACCOUNT_LIMIT,
    FORGOT_PASSWORD_LIMIT,
    LOGIN_LIMIT,
    RESET_PASSWORD_LIMIT,
    SIGNUP_LIMIT,
    limiter,
)
from ..schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)
# Imported as a module, not by symbol: tests swap send_password_reset with
# monkeypatch.setattr, which a from-import would have already bound past.
from ..services import email as email_service
from .deps import get_current_user, is_admin
from .security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against when login hits an unknown email, so both failure modes
# take a comparable amount of time.
_DUMMY_HASH = hash_password("dummy-password-for-timing")

TOKEN_BYTES = 32  # 256 bits; 43 url-safe characters

TTL_ENV = "PASSWORD_RESET_TTL_MINUTES"
# Not driven by the free-tier cold start — that wake happens between opening the
# page and submitting it, inside the client's own 60s budget. It is driven by
# delivery: an unauthenticated sender rewritten to @brevosend.com is exactly the
# profile receiving mail servers greylist, and a 5-15 minute temp-deferral on
# first contact is routine. A tidy-looking 15 minutes can therefore expire
# before the mail is readable. An hour bounds the live credential and still
# survives a bad delivery day.
DEFAULT_TTL_MINUTES = 60

# Minimum gap between sends to one account. Without it, anyone who knows an
# address can refill that inbox for as long as the per-IP limit allows.
RESEND_COOLDOWN_S = 60

GLOBAL_LIMIT_ENV = "PASSWORD_RESET_GLOBAL_DAILY_LIMIT"
# Ceiling across ALL users, same argument as AI_GLOBAL_DAILY_LIMIT: the per-IP
# limit bounds one caller, nothing bounded the total, and the provider's free
# allowance (300/day, shared with marketing sends) is what runs out. Draining it
# would mean genuine reset requests get no email at all.
DEFAULT_GLOBAL_DAILY_LIMIT = 100

# Spent rows are kept a day for "did we mail them last night?", then dropped.
PURGE_AFTER = timedelta(hours=24)

APP_BASE_URL_ENV = "APP_BASE_URL"
# The real deployed frontend, not localhost: render.yaml is not synced to the
# dashboard, so an unset variable must still produce a link that works rather
# than one that silently points at the developer's machine.
DEFAULT_APP_BASE_URL = "https://macros-calculator-mu.vercel.app"

# Identical whether or not the address has an account. Signup's 409 already
# leaks account existence and says so deliberately; that is a reason not to add
# a second, cheaper oracle here, not a reason to stop caring.
_RESET_SENT_DETAIL = (
    "If an account exists for that address, a reset link is on its way."
)
# One message for unknown, expired and already-used. They are the same
# instruction to a user, and three different messages would say which one it was.
_INVALID_RESET_DETAIL = (
    "That reset link is invalid, has expired, or has already been used. "
    "Request a new one."
)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _ttl_minutes() -> int:
    raw = os.environ.get(TTL_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_TTL_MINUTES


def _global_daily_limit() -> int:
    raw = os.environ.get(GLOBAL_LIMIT_ENV, "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_GLOBAL_DAILY_LIMIT


def _reset_url(raw_token: str) -> str:
    """Build the emailed link from configuration ONLY.

    Never from the Host, Origin or X-Forwarded-Host header. Those are attacker
    controlled, and deriving the link from them is host-header injection: the
    victim receives a real reset mail for their real account carrying a link to
    someone else's server, and hands over the token by clicking it. Reading this
    from an env var is the entire mitigation, which is why it is not a
    convenience.
    """
    base = os.environ.get(APP_BASE_URL_ENV, "").strip() or DEFAULT_APP_BASE_URL
    return f"{base.rstrip('/')}/reset-password?token={raw_token}"


def _purge_expired_resets(db: Session) -> None:
    """Drop long-dead rows. There is no scheduler, so this is the cleanup.

    Called unconditionally on every forgot-password request, before the account
    lookup, so a known and an unknown address do identical work.
    """
    db.execute(
        delete(PasswordReset).where(
            PasswordReset.expires_at < utcnow() - PURGE_AFTER
        )
    )
    db.commit()


def _may_send(db: Session, user: User) -> bool:
    """Whether to actually send, having decided the account exists.

    Both refusals are SILENT — the caller still returns the same 200. A 429 that
    fired only for real addresses would be a cleaner enumeration oracle than the
    response body we just went to the trouble of making uniform.
    """
    # Locks the user row so two concurrent requests can't both pass the cooldown
    # check. A no-op on SQLite, which serializes writes anyway; it is Postgres
    # this is for. Same device as _reserve_call in routers/ai.py.
    db.execute(select(User.id).where(User.id == user.id).with_for_update())

    cooldown_start = utcnow() - timedelta(seconds=RESEND_COOLDOWN_S)
    recent = db.scalars(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.used_at.is_(None),
            PasswordReset.created_at >= cooldown_start,
        )
    ).first()
    if recent is not None:
        logger.info("Password reset resend cooldown hit (user=%s)", user.id)
        return False

    utc_midnight = datetime.combine(datetime.now(timezone.utc).date(), time.min)
    sent_today = db.scalar(
        select(func.count())
        .select_from(PasswordReset)
        .where(PasswordReset.created_at >= utc_midnight)
    )
    limit = _global_daily_limit()
    if sent_today >= limit:
        logger.warning(
            "Global daily password-reset cap reached (%s/day); not sending "
            "for user %s",
            limit, user.id,
        )
        return False
    return True


async def _send_reset_email(user_id: int, to_email: str, reset_url: str) -> None:
    """Background wrapper around the provider call.

    Runs after the response has already been sent, which is the point: sending
    inline would make a real address measurably slower to answer than an unknown
    one, and that timing difference is the enumeration oracle the uniform
    response body exists to close.

    Two consequences of running here. Nothing may escape — an exception at this
    stage lands in the ASGI error path on a request that has already completed —
    so everything is caught. And this log line is the ONLY record that a reset
    email failed, since the user was told "check your inbox" regardless.

    Takes plain values, never the Session or a User: FastAPI closes `yield`
    dependencies before background tasks run, so an ORM instance passed in here
    would be detached from its session by the time it was touched.
    """
    try:
        await email_service.send_password_reset(
            to_email, reset_url, _ttl_minutes()
        )
        logger.info("Password reset email sent (user=%s)", user_id)
    except Exception:
        # user id, never the address: these logs live in a third-party retention
        # window, and meal_ai's standard is that no PII reaches them.
        logger.exception("Password reset email failed (user=%s)", user_id)


def _user_out(user: User) -> UserOut:
    """The one place a UserOut is built from a User row.

    Every path that returns a user goes through here. `is_admin` is computed,
    not stored, so it exists on no ORM row -- and because UserOut.is_admin has
    a default, letting Pydantic read a User directly does NOT raise. It quietly
    returns False. That is the failure this helper exists to prevent: an admin
    would be recognised on login (where the field was passed explicitly) and
    silently demoted on the next page refresh (where /me read the row).
    """
    return UserOut(id=user.id, email=user.email, is_admin=is_admin(user))


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=_user_out(user),
    )


@router.post("/signup", response_model=TokenResponse, status_code=201)
@limiter.limit(SIGNUP_LIMIT)
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.flush()  # assigns user.id, surfaces duplicate email
        db.add(Setting(user_id=user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        # This 409 is a deliberate enumeration tradeoff: without an email
        # verification flow there is no way to hide account existence at
        # signup, and a generic error would only hurt legitimate users. The
        # per-client rate limit above throttles enumeration at scale, and the
        # password was already hashed so both outcomes take comparable time.
        raise HTTPException(status_code=409, detail="Email already registered")
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.scalars(select(User).where(func.lower(User.email) == email)).first()
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    # _user_out, not `return user`: see the docstring there. Returning the ORM
    # row would type-check, pass tests that only assert id and email, and be
    # wrong for exactly one field.
    return _user_out(user)


@router.post("/change-password", response_model=TokenResponse)
@limiter.limit(ACCOUNT_LIMIT)
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    # Second precision: the fresh token below is minted in the same second and
    # must not be older than the change (deps.py rejects iat < this value).
    user.password_changed_at = utcnow().replace(microsecond=0)
    db.commit()
    # All previously issued tokens are now invalid; return a fresh one so the
    # caller's session survives the change.
    return _token_response(user)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit(FORGOT_PASSWORD_LIMIT)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Mail a reset link, if that address has an account.

    Always answers 200 with the same body either way. The whole endpoint is
    arranged around not revealing which it was: the configuration check happens
    before the lookup, the purge happens before the lookup, and the send happens
    after the response.
    """
    # Before the lookup on purpose. Checked afterwards, an unconfigured server
    # would 503 for real addresses and 200 for unknown ones, which is precisely
    # the oracle this endpoint is built to avoid. The env var name goes in the
    # log, not the response — unlike /api/ai/analyze, this route is public.
    if not email_service.is_configured():
        logger.error(
            "Password reset requested but email is not configured "
            "(%s / %s).",
            email_service.API_KEY_ENV, email_service.SENDER_EMAIL_ENV,
        )
        raise HTTPException(
            status_code=503, detail="Password reset is not available right now."
        )

    _purge_expired_resets(db)

    address = body.email.strip().lower()
    user = db.scalars(select(User).where(func.lower(User.email) == address)).first()
    if user is not None and _may_send(db, user):
        raw_token = secrets.token_urlsafe(TOKEN_BYTES)
        db.add(
            PasswordReset(
                user_id=user.id,
                token_hash=_hash_token(raw_token),
                expires_at=utcnow() + timedelta(minutes=_ttl_minutes()),
            )
        )
        db.commit()
        # user.email, not body.email: the stored address is the normalised one,
        # and mail goes only where an account already exists.
        background.add_task(
            _send_reset_email, user.id, user.email, _reset_url(raw_token)
        )

    return MessageResponse(detail=_RESET_SENT_DETAIL)


@router.post("/reset-password", status_code=204)
@limiter.limit(RESET_PASSWORD_LIMIT)
def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """Consume a reset link and set a new password.

    Returns 204 rather than a fresh token: the caller is sent to the login page
    to use the password they just chose. That keeps every setToken call site in
    the frontend's AuthContext, and means no JWT is minted in the same request
    that writes password_changed_at — see the second-precision trap documented
    on change_password above.
    """
    now = utcnow()
    record = db.scalars(
        select(PasswordReset).where(
            PasswordReset.token_hash == _hash_token(body.token)
        )
    ).first()
    user = db.get(User, record.user_id) if record is not None else None

    # A token is dead if it was spent, has expired, its account is gone, or the
    # password has changed since it was issued. That last clause is what makes
    # /change-password invalidate outstanding links without /change-password
    # knowing this table exists — the same rule deps.py applies to JWTs.
    if (
        record is None
        or user is None
        or record.used_at is not None
        or record.expires_at <= now
        or (
            user.password_changed_at is not None
            # Both sides truncated to whole seconds before comparing.
            # password_changed_at already is (JWT `iat` is a whole-second claim,
            # see change_password), so comparing it against a microsecond
            # precision created_at would let a link issued earlier in the same
            # second as a password change outlive that change. Ties go to
            # rejecting the link: the cost of being wrong is one extra "request
            # a new link", and it can only happen inside a one-second window.
            and user.password_changed_at >= record.created_at.replace(microsecond=0)
        )
    ):
        raise HTTPException(status_code=400, detail=_INVALID_RESET_DETAIL)

    # Hashing happens only after the token checks out. Argon2 is expensive by
    # design, and this endpoint is unauthenticated: hashing first would let
    # anyone spend a free instance's CPU by posting garbage tokens.
    user.password_hash = hash_password(body.new_password)
    # Second precision, matching change_password, even though nothing is minted
    # here — it keeps the column's documented contract and defuses the trap in
    # advance for anyone who later makes this endpoint return a token.
    user.password_changed_at = utcnow().replace(microsecond=0)

    # Burn every outstanding link, not just this one. password_changed_at alone
    # nearly covers it, but it is truncated to whole seconds: a sibling token
    # created 300ms earlier in the same second would compare as newer than the
    # change and survive.
    for row in db.scalars(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.used_at.is_(None),
        )
    ):
        row.used_at = now
    db.commit()


@router.delete("/account", status_code=204)
@limiter.limit(ACCOUNT_LIMIT)
def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the account; FK cascades remove all owned data."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    db.delete(user)
    db.commit()
