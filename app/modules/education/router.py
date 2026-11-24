from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...deps import get_current_user, get_tenant_id
from ...errors import AppError
from ...models import Enrollment, Resource, User

router = APIRouter()


class ResourceIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    category: str = Field(default="guide", max_length=80)
    level: str = Field(default="beginner", max_length=30)
    body: str | None = None
    is_published: bool = True


class ResourceOut(BaseModel):
    id: int
    title: str
    category: str
    level: str
    body: str | None
    is_published: bool

    model_config = {"from_attributes": True}


class EnrollmentIn(BaseModel):
    resource_id: int


class EnrollmentOut(BaseModel):
    id: int
    resource_id: int
    user_id: int
    status: str
    progress: int
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/resources", response_model=list[ResourceOut])
def list_resources(db: Session = Depends(get_db)) -> list[ResourceOut]:
    rows = db.query(Resource).filter(Resource.is_published.is_(True)).all()
    return [ResourceOut.model_validate(row) for row in rows]


@router.post("/resources", response_model=ResourceOut, status_code=201)
def create_resource(
    payload: ResourceIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ResourceOut:
    resource = Resource(tenant_id=tenant_id, **payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return ResourceOut.model_validate(resource)


@router.post("/enrollments", response_model=EnrollmentOut, status_code=201)
def enroll(
    payload: EnrollmentIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> EnrollmentOut:
    resource = db.query(Resource).filter(Resource.id == payload.resource_id).first()
    if resource is None:
        raise AppError(404, "Resource not found", "not_found")
    existing = (
        db.query(Enrollment)
        .filter(Enrollment.resource_id == payload.resource_id, Enrollment.user_id == user.id)
        .first()
    )
    if existing:
        return EnrollmentOut.model_validate(existing)
    enrollment = Enrollment(tenant_id=tenant_id, resource_id=payload.resource_id, user_id=user.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return EnrollmentOut.model_validate(enrollment)


@router.patch("/enrollments/{enrollment_id}/progress", response_model=EnrollmentOut)
def update_progress(
    enrollment_id: int,
    progress: int = Query(ge=0, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EnrollmentOut:
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id, Enrollment.user_id == user.id)
        .first()
    )
    if enrollment is None:
        raise AppError(404, "Enrollment not found", "not_found")
    enrollment.progress = progress
    if progress == 100:
        enrollment.status = "completed"
    db.commit()
    db.refresh(enrollment)
    return EnrollmentOut.model_validate(enrollment)


@router.get("/enrollments", response_model=list[EnrollmentOut])
def my_enrollments(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[EnrollmentOut]:
    rows = db.query(Enrollment).filter(Enrollment.user_id == user.id).all()
    return [EnrollmentOut.model_validate(row) for row in rows]
