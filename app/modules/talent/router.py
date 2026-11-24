from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...deps import get_tenant_id, require_roles
from ...errors import AppError
from ...models import Application, Opportunity, User

router = APIRouter()


class OpportunityIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    category: str = Field(default="internship", max_length=80)
    location: str | None = Field(default=None, max_length=120)
    description: str | None = None
    deadline: datetime | None = None
    is_active: bool = True


class OpportunityOut(BaseModel):
    id: int
    title: str
    organization: str | None
    category: str
    location: str | None
    description: str | None
    deadline: datetime | None
    is_active: bool

    model_config = {"from_attributes": True}


class ApplicationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    cover_letter: str | None = None


class ApplicationOut(BaseModel):
    id: int
    opportunity_id: int
    name: str
    email: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(db: Session = Depends(get_db)) -> list[OpportunityOut]:
    rows = db.query(Opportunity).filter(Opportunity.is_active.is_(True)).all()
    return [OpportunityOut.model_validate(row) for row in rows]


@router.post("/opportunities", response_model=OpportunityOut, status_code=201)
def create_opportunity(
    payload: OpportunityIn,
    user: User = Depends(require_roles("owner", "admin")),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> OpportunityOut:
    opportunity = Opportunity(tenant_id=tenant_id, **payload.model_dump())
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)
    return OpportunityOut.model_validate(opportunity)


@router.post("/opportunities/{opportunity_id}/apply", response_model=ApplicationOut, status_code=201)
def apply(
    opportunity_id: int,
    payload: ApplicationIn,
    db: Session = Depends(get_db),
) -> ApplicationOut:
    opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id, Opportunity.is_active.is_(True)).first()
    if opportunity is None:
        raise AppError(404, "Opportunity not found", "not_found")
    application = Application(
        tenant_id=opportunity.tenant_id,
        opportunity_id=opportunity_id,
        **payload.model_dump(),
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return ApplicationOut.model_validate(application)


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[ApplicationOut]:
    rows = db.query(Application).filter(Application.tenant_id == tenant_id).all()
    return [ApplicationOut.model_validate(row) for row in rows]


@router.patch("/applications/{application_id}/status", response_model=ApplicationOut)
def update_application_status(
    application_id: int,
    status: str = Query(pattern="^(submitted|reviewing|shortlisted|rejected|accepted)$"),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.tenant_id == tenant_id)
        .first()
    )
    if application is None:
        raise AppError(404, "Application not found", "not_found")
    application.status = status
    db.commit()
    db.refresh(application)
    return ApplicationOut.model_validate(application)
