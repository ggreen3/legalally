from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...deps import get_current_user, get_tenant_id, require_roles
from ...errors import AppError
from ...models import (
    AuditLog,
    Client,
    Document,
    Invoice,
    InvoiceItem,
    LegalCase,
    Subscription,
    TimeEntry,
    User,
    Waitlist,
)

router = APIRouter()


def tenant_record(db: Session, model, tenant_id: int, record_id: int):
    record = db.query(model).filter(model.id == record_id, model.tenant_id == tenant_id).first()
    if record is None:
        raise AppError(404, "Resource not found", "not_found")
    return record


class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    identification: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class ClientOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    identification: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    client_id: int | None = None
    case_number: str | None = Field(default=None, max_length=100)
    category: str = Field(default="general", max_length=100)
    status: str = Field(default="open", max_length=30)
    description: str | None = None


class CaseOut(BaseModel):
    id: int
    client_id: int | None
    title: str
    case_number: str | None
    category: str
    status: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    case_id: int | None = None
    doc_type: str = Field(default="general", max_length=80)
    content: str | None = None
    is_confidential: bool = True


class DocumentOut(BaseModel):
    id: int
    case_id: int | None
    title: str
    doc_type: str
    version: int
    is_confidential: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TimeEntryIn(BaseModel):
    case_id: int
    description: str = Field(min_length=3)
    minutes: int = Field(ge=1, le=100000)
    rate_cents: int = Field(default=0, ge=0)
    billable: bool = True


class TimeEntryOut(BaseModel):
    id: int
    case_id: int
    description: str
    minutes: int
    rate_cents: int
    billable: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceItemIn(BaseModel):
    description: str = Field(min_length=2, max_length=300)
    quantity: int = Field(default=1, ge=1)
    unit_price_cents: int = Field(default=0, ge=0)


class InvoiceIn(BaseModel):
    client_id: int
    case_id: int | None = None
    items: list[InvoiceItemIn] = Field(min_length=1)
    due_in_days: int = Field(default=14, ge=0, le=365)


class InvoiceOut(BaseModel):
    id: int
    number: str
    client_id: int
    case_id: int | None
    status: str
    total_cents: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionOut(BaseModel):
    tier: str
    status: str
    monthly_price_cents: int
    starts_at: datetime
    ends_at: datetime | None

    model_config = {"from_attributes": True}


class WaitlistIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    role: str | None = Field(default=None, max_length=80)


class WaitlistOut(BaseModel):
    id: int
    name: str
    email: str
    role: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/overview")
def overview(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return {
        "clients": db.query(Client).filter(Client.tenant_id == tenant_id).count(),
        "cases": db.query(LegalCase).filter(LegalCase.tenant_id == tenant_id).count(),
        "documents": db.query(Document).filter(Document.tenant_id == tenant_id).count(),
        "invoices": db.query(Invoice).filter(Invoice.tenant_id == tenant_id).count(),
        "open_cases": db.query(LegalCase)
        .filter(LegalCase.tenant_id == tenant_id, LegalCase.status == "open")
        .count(),
    }


@router.get("/clients", response_model=list[ClientOut])
def list_clients(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[ClientOut]:
    rows = db.query(Client).filter(Client.tenant_id == tenant_id).order_by(Client.created_at.desc()).all()
    return [ClientOut.model_validate(row) for row in rows]


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(
    payload: ClientIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ClientOut:
    client = Client(tenant_id=tenant_id, **payload.model_dump())
    db.add(client)
    db.add(AuditLog(tenant_id=tenant_id, user_id=user.id, action="briefcase.client.create", entity="clients"))
    db.commit()
    db.refresh(client)
    return ClientOut.model_validate(client)


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> ClientOut:
    return ClientOut.model_validate(tenant_record(db, Client, tenant_id, client_id))


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(
    client_id: int,
    payload: ClientIn,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ClientOut:
    client = tenant_record(db, Client, tenant_id, client_id)
    for key, value in payload.model_dump().items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return ClientOut.model_validate(client)


@router.delete("/clients/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    db.delete(tenant_record(db, Client, tenant_id, client_id))
    db.commit()


@router.get("/cases", response_model=list[CaseOut])
def list_cases(
    status: str | None = Query(default=None),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[CaseOut]:
    query = db.query(LegalCase).filter(LegalCase.tenant_id == tenant_id)
    if status:
        query = query.filter(LegalCase.status == status)
    return [CaseOut.model_validate(row) for row in query.order_by(LegalCase.created_at.desc()).all()]


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(
    payload: CaseIn,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CaseOut:
    if payload.client_id:
        tenant_record(db, Client, tenant_id, payload.client_id)
    case = LegalCase(tenant_id=tenant_id, **payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return CaseOut.model_validate(case)


@router.patch("/cases/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int,
    payload: CaseIn,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CaseOut:
    case = tenant_record(db, LegalCase, tenant_id, case_id)
    for key, value in payload.model_dump().items():
        setattr(case, key, value)
    db.commit()
    db.refresh(case)
    return CaseOut.model_validate(case)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: int, tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> None:
    db.delete(tenant_record(db, LegalCase, tenant_id, case_id))
    db.commit()


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[DocumentOut]:
    rows = db.query(Document).filter(Document.tenant_id == tenant_id).order_by(Document.created_at.desc()).all()
    return [DocumentOut.model_validate(row) for row in rows]


@router.post("/documents", response_model=DocumentOut, status_code=201)
def create_document(
    payload: DocumentIn,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> DocumentOut:
    if payload.case_id:
        tenant_record(db, LegalCase, tenant_id, payload.case_id)
    document = Document(tenant_id=tenant_id, **payload.model_dump())
    db.add(document)
    db.commit()
    db.refresh(document)
    return DocumentOut.model_validate(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> None:
    db.delete(tenant_record(db, Document, tenant_id, document_id))
    db.commit()


@router.get("/time-entries", response_model=list[TimeEntryOut])
def list_time_entries(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[TimeEntryOut]:
    rows = db.query(TimeEntry).filter(TimeEntry.tenant_id == tenant_id).order_by(TimeEntry.created_at.desc()).all()
    return [TimeEntryOut.model_validate(row) for row in rows]


@router.post("/time-entries", response_model=TimeEntryOut, status_code=201)
def create_time_entry(
    payload: TimeEntryIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TimeEntryOut:
    tenant_record(db, LegalCase, tenant_id, payload.case_id)
    entry = TimeEntry(tenant_id=tenant_id, user_id=user.id, **payload.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return TimeEntryOut.model_validate(entry)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[InvoiceOut]:
    rows = db.query(Invoice).filter(Invoice.tenant_id == tenant_id).order_by(Invoice.created_at.desc()).all()
    return [InvoiceOut.model_validate(row) for row in rows]


@router.post("/invoices", response_model=InvoiceOut, status_code=201)
def create_invoice(
    payload: InvoiceIn,
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> InvoiceOut:
    tenant_record(db, Client, tenant_id, payload.client_id)
    number = f"INV-{tenant_id}-{datetime.now(UTC).year}-{uuid.uuid4().hex[:8].upper()}"
    total = sum(item.quantity * item.unit_price_cents for item in payload.items)
    invoice = Invoice(
        tenant_id=tenant_id,
        client_id=payload.client_id,
        case_id=payload.case_id,
        number=number,
        status="draft",
        total_cents=total,
        due_date=datetime.now(UTC) + timedelta(days=payload.due_in_days),
    )
    db.add(invoice)
    db.flush()
    for item in payload.items:
        db.add(InvoiceItem(invoice_id=invoice.id, **item.model_dump()))
    db.commit()
    db.refresh(invoice)
    return InvoiceOut.model_validate(invoice)


@router.patch("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    status: str = Query(pattern="^(draft|sent|paid|void)$"),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> InvoiceOut:
    invoice = tenant_record(db, Invoice, tenant_id, invoice_id)
    invoice.status = status
    db.commit()
    db.refresh(invoice)
    return InvoiceOut.model_validate(invoice)


@router.get("/subscription", response_model=SubscriptionOut)
def subscription(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> SubscriptionOut:
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub is None:
        raise AppError(404, "Subscription not found", "not_found")
    return SubscriptionOut.model_validate(sub)


@router.post("/waitlist", status_code=201)
def join_waitlist(payload: WaitlistIn, db: Session = Depends(get_db)) -> dict:
    email = str(payload.email).strip().lower()
    if db.query(Waitlist).filter(Waitlist.email == email).first():
        raise AppError(409, "Already on the waitlist", "conflict")
    data = payload.model_dump()
    data["name"] = data["name"].strip()
    data["email"] = email
    data["role"] = data["role"].strip() if data["role"] else None
    db.add(Waitlist(**data))
    db.commit()
    return {"status": "registered"}


@router.get("/waitlist", response_model=list[WaitlistOut])
def list_waitlist(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> list[WaitlistOut]:
    rows = db.query(Waitlist).order_by(Waitlist.created_at.desc(), Waitlist.id.desc()).all()
    return [WaitlistOut.model_validate(row) for row in rows]


@router.get("/waitlist/export", response_class=PlainTextResponse)
def export_waitlist(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> str:
    rows = db.query(Waitlist).order_by(Waitlist.created_at.desc(), Waitlist.id.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "email", "role", "created_at"])
    for row in rows:
        writer.writerow([row.id, row.name, row.email, row.role or "", row.created_at.isoformat()])
    return output.getvalue()
