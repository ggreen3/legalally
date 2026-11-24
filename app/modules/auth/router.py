from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...deps import get_current_user
from ...errors import AppError
from ...models import Subscription, Tenant, User
from ...security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    rate_limiter,
    verify_password,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    tenant_id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tenant"


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == payload.email).first():
        raise AppError(409, "Email already registered", "conflict")
    base_slug = slugify(payload.tenant_name)
    slug = base_slug
    suffix = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        suffix += 1
        slug = f"{base_slug}-{suffix}"
    tenant = Tenant(name=payload.tenant_name, slug=slug, tier="starter")
    db.add(tenant)
    db.flush()
    db.add(
        Subscription(
            tenant_id=tenant.id,
            tier="starter",
            status="active",
            monthly_price_cents=200000,
            starts_at=datetime.now(UTC),
        )
    )
    user = User(
        tenant_id=tenant.id,
        email=str(payload.email),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role="owner",
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if not rate_limiter.check(f"login:{payload.email}", limit=10, window=60):
        raise AppError(429, "Too many login attempts", "rate_limited")
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise AppError(401, "Invalid email or password", "invalid_credentials")
    if not user.is_active:
        raise AppError(403, "Account is inactive", "forbidden")
    return TokenResponse(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_data = decode_token(payload.refresh_token, "refresh")
    user = db.get(User, int(token_data["sub"]))
    if not user or not user.is_active:
        raise AppError(401, "Account not found or inactive", "unauthorized")
    return TokenResponse(
        access_token=create_access_token(user.id, user.tenant_id, user.role),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
