from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .db import get_db
from .errors import AppError
from .models import User
from .security import decode_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(401, "Authentication required", "unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token, "access")
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise AppError(401, "Invalid token subject", "unauthorized") from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise AppError(401, "Account not found or inactive", "unauthorized")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise AppError(403, "Insufficient permissions", "forbidden")
        return user

    return dependency


def get_tenant_id(user: User = Depends(get_current_user)) -> int:
    return user.tenant_id
