import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


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
