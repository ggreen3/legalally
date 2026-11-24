from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...deps import get_current_user, get_tenant_id, require_roles
from ...errors import AppError
from ...models import Innovation, User

router = APIRouter()


class InnovationIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    sector: str | None = Field(default=None, max_length=100)
    stage: str = Field(default="idea", max_length=50)


class InnovationOut(BaseModel):
    id: int
    title: str
    description: str | None
    sector: str | None
    stage: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[InnovationOut])
def list_innovations(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[InnovationOut]:
    rows = db.query(Innovation).filter(Innovation.tenant_id == tenant_id).all()
    return [InnovationOut.model_validate(row) for row in rows]


@router.post("/", response_model=InnovationOut, status_code=201)
def submit_innovation(
    payload: InnovationIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> InnovationOut:
    innovation = Innovation(tenant_id=tenant_id, submitted_by=user.full_name, **payload.model_dump())
    db.add(innovation)
    db.commit()
    db.refresh(innovation)
    return InnovationOut.model_validate(innovation)


@router.patch("/{innovation_id}/status", response_model=InnovationOut)
def review_innovation(
    innovation_id: int,
    status: str = Query(pattern="^(submitted|reviewing|accepted|rejected)$"),
    tenant_id: int = Depends(get_tenant_id),
    user: User = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
) -> InnovationOut:
    innovation = (
        db.query(Innovation)
        .filter(Innovation.id == innovation_id, Innovation.tenant_id == tenant_id)
        .first()
    )
    if innovation is None:
        raise AppError(404, "Innovation not found", "not_found")
    innovation.status = status
    db.commit()
    db.refresh(innovation)
    return InnovationOut.model_validate(innovation)
