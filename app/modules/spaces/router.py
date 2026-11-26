from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ...db import get_db
from ...deps import get_current_user
from ...errors import AppError
from ...models import AuditLog, OfficeSpace, SpaceEnquiry, User
from ...security import rate_limiter

router = APIRouter()

SPACE_TYPES = {"serviced", "shared", "shortlet", "lease", "meeting"}
TERMS = {"hourly", "daily", "monthly", "quarterly", "yearly"}


class SpaceOut(BaseModel):
    id: int
    slug: str
    title: str
    city: str
    area: str
    space_type: str
    term: str
    price_cents: int
    capacity: int
    bedrooms: int
    bathrooms: int
    description: str
    amenities: list[str]
    highlights: list[str]
    accent: str
    available_from: str | None
    featured: bool


class SpaceCreate(BaseModel):
    title: str = Field(min_length=6, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    area: str = Field(min_length=2, max_length=120)
    space_type: str = Field(pattern="^(serviced|shared|shortlet|lease|meeting)$")
    term: str = Field(pattern="^(hourly|daily|monthly|quarterly|yearly)$")
    price_cents: int = Field(gt=0)
    capacity: int = Field(ge=1)
    bedrooms: int = Field(ge=0)
    bathrooms: int = Field(ge=0)
    description: str = Field(min_length=20, max_length=4000)
    amenities: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    available_from: str | None = Field(default=None, max_length=40)


class EnquiryCreate(BaseModel):
    start_date: str = Field(min_length=3, max_length=40)
    term: str = Field(pattern="^(hourly|daily|monthly|quarterly|yearly)$")
    message: str | None = Field(default=None, max_length=2000)
    contact_email: str = Field(min_length=5, max_length=255)


class EnquiryOut(BaseModel):
    id: int
    space_id: int
    space_title: str
    start_date: str
    term: str
    status: str
    created_at: datetime


def serialize(space: OfficeSpace) -> SpaceOut:
    return SpaceOut(
        id=space.id,
        slug=space.slug,
        title=space.title,
        city=space.city,
        area=space.area,
        space_type=space.space_type,
        term=space.term,
        price_cents=space.price_cents,
        capacity=space.capacity,
        bedrooms=space.bedrooms,
        bathrooms=space.bathrooms,
        description=space.description,
        amenities=space.amenities or [],
        highlights=space.highlights or [],
        accent=space.accent or "teal",
        available_from=space.available_from,
        featured=bool(space.featured),
    )


def make_slug(title: str, db: Session) -> str:
    parts = ["".join(char for char in word.lower() if char.isalnum()) for word in title.split()]
    base = "-".join(part for part in parts if part)[:60] or "office-space"
    slug = base
    while db.query(OfficeSpace).filter(OfficeSpace.slug == slug).first() is not None:
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    return slug


@router.get("/filters")
def filters(db: Session = Depends(get_db)) -> dict[str, object]:
    cities = [row[0] for row in db.query(OfficeSpace.city).distinct().order_by(OfficeSpace.city).all()]
    prices = db.query(func.min(OfficeSpace.price_cents), func.max(OfficeSpace.price_cents)).first()
    return {
        "cities": cities,
        "types": sorted(SPACE_TYPES),
        "terms": sorted(TERMS),
        "min_price_cents": prices[0] or 0,
        "max_price_cents": prices[1] or 0,
    }


@router.get("", response_model=list[SpaceOut])
def list_spaces(
    q: str | None = None,
    city: str | None = None,
    space_type: str | None = None,
    term: str | None = None,
    max_price_cents: int | None = None,
    min_capacity: int | None = None,
    sort: str = "featured",
    db: Session = Depends(get_db),
) -> list[SpaceOut]:
    query = db.query(OfficeSpace).filter(OfficeSpace.status == "available")
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            func.lower(OfficeSpace.title).like(pattern.lower())
            | func.lower(OfficeSpace.city).like(pattern.lower())
            | func.lower(OfficeSpace.area).like(pattern.lower())
            | func.lower(OfficeSpace.description).like(pattern.lower())
        )
    if city:
        query = query.filter(func.lower(OfficeSpace.city).like(f"%{city.strip().lower()}%"))
    if space_type:
        query = query.filter(OfficeSpace.space_type == space_type)
    if term:
        query = query.filter(OfficeSpace.term == term)
    if max_price_cents is not None:
        query = query.filter(OfficeSpace.price_cents <= max_price_cents)
    if min_capacity is not None:
        query = query.filter(OfficeSpace.capacity >= min_capacity)
    if sort == "price_asc":
        query = query.order_by(OfficeSpace.price_cents.asc())
    elif sort == "price_desc":
        query = query.order_by(OfficeSpace.price_cents.desc())
    elif sort == "capacity":
        query = query.order_by(OfficeSpace.capacity.desc())
    else:
        query = query.order_by(OfficeSpace.featured.desc(), OfficeSpace.created_at.desc())
    return [serialize(space) for space in query.limit(60).all()]


@router.get("/mine/enquiries", response_model=list[EnquiryOut])
def my_enquiries(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EnquiryOut]:
    rows = (
        db.query(SpaceEnquiry, OfficeSpace.title)
        .join(OfficeSpace, OfficeSpace.id == SpaceEnquiry.space_id)
        .filter(SpaceEnquiry.tenant_id == user.tenant_id, SpaceEnquiry.user_id == user.id)
        .order_by(SpaceEnquiry.created_at.desc())
        .limit(30)
        .all()
    )
    return [
        EnquiryOut(
            id=enquiry.id,
            space_id=enquiry.space_id,
            space_title=title,
            start_date=enquiry.start_date,
            term=enquiry.term,
            status=enquiry.status,
            created_at=enquiry.created_at,
        )
        for enquiry, title in rows
    ]


@router.post("", response_model=SpaceOut, status_code=201)
def create_space(
    payload: SpaceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpaceOut:
    if not rate_limiter.check(f"spaces:create:{user.tenant_id}", limit=20):
        raise AppError(429, "Too many listings created", "rate_limited")
    space = OfficeSpace(
        owner_tenant_id=user.tenant_id,
        title=payload.title.strip(),
        slug=make_slug(payload.title, db),
        city=payload.city.strip(),
        area=payload.area.strip(),
        space_type=payload.space_type,
        term=payload.term,
        price_cents=payload.price_cents,
        capacity=payload.capacity,
        bedrooms=payload.bedrooms,
        bathrooms=payload.bathrooms,
        description=payload.description.strip(),
        amenities=[value.strip() for value in payload.amenities if value and value.strip()][:20],
        highlights=[value.strip() for value in payload.highlights if value and value.strip()][:10],
        accent="violet",
        available_from=payload.available_from,
        status="available",
    )
    db.add(space)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="space.listing.created",
            entity="office_space",
            metadata_json={"slug": space.slug, "price_cents": space.price_cents},
        )
    )
    db.commit()
    db.refresh(space)
    return serialize(space)


@router.get("/{slug}", response_model=SpaceOut)
def get_space(slug: str, db: Session = Depends(get_db)) -> SpaceOut:
    space = db.query(OfficeSpace).filter(OfficeSpace.slug == slug, OfficeSpace.status == "available").first()
    if space is None:
        raise AppError(404, "Office space not found", "not_found")
    return serialize(space)


@router.post("/{slug}/enquiries", response_model=EnquiryOut, status_code=201)
def create_enquiry(
    slug: str,
    payload: EnquiryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnquiryOut:
    if not rate_limiter.check(f"spaces:enquiry:{user.tenant_id}", limit=12):
        raise AppError(429, "Too many enquiries submitted", "rate_limited")
    space = db.query(OfficeSpace).filter(OfficeSpace.slug == slug, OfficeSpace.status == "available").first()
    if space is None:
        raise AppError(404, "Office space not found", "not_found")
    enquiry = SpaceEnquiry(
        tenant_id=user.tenant_id,
        user_id=user.id,
        space_id=space.id,
        start_date=payload.start_date.strip(),
        term=payload.term,
        message=(payload.message or "").strip() or None,
        contact_email=payload.contact_email.strip(),
        status="new",
    )
    db.add(enquiry)
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action="space.enquiry.created",
            entity="office_space",
            entity_id=space.id,
            metadata_json={"slug": space.slug, "term": payload.term},
        )
    )
    db.commit()
    db.refresh(enquiry)
    return EnquiryOut(
        id=enquiry.id,
        space_id=space.id,
        space_title=space.title,
        start_date=enquiry.start_date,
        term=enquiry.term,
        status=enquiry.status,
        created_at=enquiry.created_at,
    )
