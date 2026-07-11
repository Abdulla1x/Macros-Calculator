from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Setting, User, utcnow
from ..rate_limit import ACCOUNT_LIMIT, LOGIN_LIMIT, SIGNUP_LIMIT, limiter
from ..schemas import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
)
from .deps import get_current_user
from .security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against when login hits an unknown email, so both failure modes
# take a comparable amount of time.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserOut(id=user.id, email=user.email),
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
    return user


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
