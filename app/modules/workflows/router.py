from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...db import get_db
from ...deps import get_current_user, get_tenant_id
from ...errors import AppError
from ...models import (
    AiOutput,
    AuditLog,
    CddRecord,
    Client,
    ConflictCheck,
    CpdRecord,
    DraftTemplate,
    LegalCase,
    LegalGuide,
    MatterTask,
    TrustTransaction,
    User,
)
from ...pico import stream_pico
from ...security import rate_limiter

router = APIRouter()


class OutModel(BaseModel):
    model_config = {"from_attributes": True}


class GuideOut(OutModel):
    key: str
    title: str
    audience: str
    topic: str
    summary: str
    body: dict[str, Any]
    sources: list[dict[str, Any]]
    last_checked: datetime


class ConflictIn(BaseModel):
    client_name: str = Field(min_length=2, max_length=200)
    adverse_parties: list[str] = Field(default_factory=list, max_length=10)
    matter_title: str | None = Field(default=None, max_length=200)


class ConflictOut(OutModel):
    id: int
    status: str
    result: dict[str, Any]
    created_at: datetime


class CddIn(BaseModel):
    client_id: int
    checklist: dict[str, bool] = Field(default_factory=dict)
    risk_tier: str = Field(default="standard", pattern="^(low|standard|enhanced)$")
    reviewed_by: str | None = Field(default=None, max_length=120)


class CddOut(OutModel):
    id: int
    client_id: int
    status: str
    risk_tier: str
    checklist: dict[str, Any]
    reviewed_at: datetime | None
    updated_at: datetime


class TaskIn(BaseModel):
    case_id: int
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    due_at: datetime | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    category: str = Field(default="deadline", max_length=60)
    owner: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=200)


class TaskOut(OutModel):
    id: int
    case_id: int
    title: str
    description: str | None
    due_at: datetime | None
    status: str
    priority: str
    category: str
    owner: str | None
    source: str | None
    created_at: datetime


class TaskStatusIn(BaseModel):
    status: str = Field(pattern="^(open|done|cancelled)$")


class TrustIn(BaseModel):
    case_id: int
    client_id: int
    kind: str = Field(pattern="^(receipt|payment)$")
    amount_cents: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=120)
    posted_by: str | None = Field(default=None, max_length=120)


class TrustOut(OutModel):
    id: int
    case_id: int
    client_id: int
    kind: str
    amount_cents: int
    reference: str | None
    posted_by: str | None
    balance_cents: int
    created_at: datetime


class FeeIn(BaseModel):
    hours: float = Field(gt=0, le=1000)
    hourly_rate_cents: int = Field(gt=0)
    disbursements_cents: int = Field(default=0, ge=0)
    vat_rate: float = Field(default=8, ge=0, le=30)


class FeeOut(BaseModel):
    fees_cents: int
    disbursements_cents: int
    subtotal_cents: int
    vat_cents: int
    total_cents: int
    note: str


class TemplateOut(OutModel):
    key: str
    title: str
    category: str
    body: str
    variables: list[str]


class TemplateDraftIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    case_id: int | None = None


class TemplateDraftOut(BaseModel):
    output_id: int
    title: str
    draft: str
    notice: str


class VerifyIn(BaseModel):
    verified_by: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class VerifyOut(OutModel):
    id: int
    verified_by: str | None
    verified_at: datetime | None


class CpdIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    provider: str | None = Field(default=None, max_length=200)
    units: int = Field(default=1, gt=0, le=100)
    evidence_url: str | None = Field(default=None, max_length=300)
    completed_at: datetime | None = None


class CpdOut(OutModel):
    id: int
    title: str
    provider: str | None
    units: int
    evidence_url: str | None
    completed_at: datetime


def audit(
    db: Session,
    tenant_id: int,
    user_id: int,
    action: str,
    entity: str,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity=entity,
            metadata_json=metadata_json,
        )
    )


def tenant_case(db: Session, case_id: int, tenant_id: int) -> LegalCase:
    record = db.query(LegalCase).filter(LegalCase.id == case_id, LegalCase.tenant_id == tenant_id).first()
    if record is None:
        raise AppError(404, "Matter not found", "not_found")
    return record


def tenant_client(db: Session, client_id: int, tenant_id: int) -> Client:
    record = db.query(Client).filter(Client.id == client_id, Client.tenant_id == tenant_id).first()
    if record is None:
        raise AppError(404, "Client not found", "not_found")
    return record


def normalise_name(value: str) -> str:
    return " ".join(value.lower().replace(",", " ").split())


def name_tokens(value: str) -> set[str]:
    stopwords = {"limited", "ltd", "company", "co", "inc", "incorporated", "the", "and", "of"}
    return {token for token in normalise_name(value).split() if token not in stopwords and len(token) > 3}


def names_overlap(first: str, second: str) -> bool:
    first_tokens = name_tokens(first)
    second_tokens = name_tokens(second)
    return bool(first_tokens & second_tokens)


def trust_out(row: TrustTransaction, balance_cents: int) -> TrustOut:
    return TrustOut(
        id=row.id,
        case_id=row.case_id,
        client_id=row.client_id,
        kind=row.kind,
        amount_cents=row.amount_cents,
        reference=row.reference,
        posted_by=row.posted_by,
        balance_cents=balance_cents,
        created_at=row.created_at,
    )


async def discard_chunk(text: str) -> None:
    return None


@router.get("/guides", response_model=list[GuideOut])
def list_guides(
    audience: str | None = Query(default=None, max_length=80),
    topic: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> list[GuideOut]:
    query = db.query(LegalGuide)
    if audience:
        query = query.filter(LegalGuide.audience == audience)
    if topic:
        query = query.filter(LegalGuide.topic == topic)
    guides = query.order_by(LegalGuide.audience, LegalGuide.title).all()
    return [GuideOut.model_validate(guide) for guide in guides]


@router.get("/guides/{key}", response_model=GuideOut)
def get_guide(key: str, db: Session = Depends(get_db)) -> GuideOut:
    guide = db.query(LegalGuide).filter(LegalGuide.key == key).first()
    if guide is None:
        raise AppError(404, "Guide not found", "not_found")
    return GuideOut.model_validate(guide)


@router.post("/conflict-check", response_model=ConflictOut)
def create_conflict_check(
    payload: ConflictIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ConflictOut:
    clients = db.query(Client).filter(Client.tenant_id == tenant_id).all()
    client_names = [normalise_name(client.name) for client in clients]
    matters = db.query(LegalCase).filter(LegalCase.tenant_id == tenant_id).all()
    matter_names = [normalise_name(matter.title) for matter in matters]

    client_hits = [client.name for client in clients if names_overlap(payload.client_name, client.name)]
    adverse_hits: list[str] = []
    for party in payload.adverse_parties:
        for name in client_names + matter_names:
            if names_overlap(party, name):
                adverse_hits.append(party)
                break
    prior = (
        db.query(ConflictCheck)
        .filter(ConflictCheck.tenant_id == tenant_id)
        .order_by(ConflictCheck.created_at.desc())
        .limit(50)
        .all()
    )
    for record in prior:
        for party in payload.adverse_parties:
            if any(names_overlap(party, item) for item in record.adverse_parties):
                adverse_hits.append(f"Prior check #{record.id}: {party}")

    unique_client_hits = list(dict.fromkeys(client_hits))
    unique_adverse_hits = list(dict.fromkeys(adverse_hits))
    has_hits = bool(unique_client_hits or unique_adverse_hits)
    result = {
        "client_hits": unique_client_hits,
        "adverse_hits": unique_adverse_hits,
        "recommendation": (
            "Do not accept the instruction until a responsible advocate reviews and clears the named overlaps."
            if has_hits
            else "No name-based overlap found in LegAlly records. Record manual registry and corporate searches before clearance."
        ),
        "scope": "LegAlly tenant records only; not a company registry, court registry or beneficial-ownership search.",
    }
    record = ConflictCheck(
        tenant_id=tenant_id,
        user_id=user.id,
        client_name=payload.client_name,
        adverse_parties=payload.adverse_parties,
        result=result,
        status="review" if has_hits else "clear",
    )
    db.add(record)
    db.flush()
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.conflict_check",
        "conflict_checks",
        {"id": record.id, "status": record.status, "matter_title": payload.matter_title},
    )
    db.commit()
    db.refresh(record)
    return ConflictOut.model_validate(record)


@router.get("/conflict-checks", response_model=list[ConflictOut])
def list_conflict_checks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
) -> list[ConflictOut]:
    records = (
        db.query(ConflictCheck)
        .filter(ConflictCheck.tenant_id == tenant_id)
        .order_by(ConflictCheck.created_at.desc())
        .limit(25)
        .all()
    )
    return [ConflictOut.model_validate(record) for record in records]


@router.post("/cdd", response_model=CddOut)
def upsert_cdd(
    payload: CddIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CddOut:
    tenant_client(db, payload.client_id, tenant_id)
    required = ["identity_verified", "beneficial_owner_checked", "purpose_recorded", "risk_reason_recorded"]
    checklist = {key: bool(payload.checklist.get(key, False)) for key in required}
    checklist.update({key: bool(value) for key, value in payload.checklist.items() if key not in required})
    complete = all(checklist[key] for key in required)
    record = (
        db.query(CddRecord)
        .filter(CddRecord.tenant_id == tenant_id, CddRecord.client_id == payload.client_id)
        .first()
    )
    if record is None:
        record = CddRecord(tenant_id=tenant_id, client_id=payload.client_id, checklist=checklist)
        db.add(record)
    record.checklist = checklist
    record.risk_tier = payload.risk_tier
    record.status = "complete" if complete else "incomplete"
    record.reviewed_by = payload.reviewed_by or user.full_name
    record.reviewed_at = datetime.now(UTC) if complete else None
    db.flush()
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.cdd.save",
        "cdd_records",
        {"client_id": payload.client_id, "status": record.status, "risk_tier": record.risk_tier},
    )
    db.commit()
    db.refresh(record)
    return CddOut.model_validate(record)


@router.get("/cdd", response_model=list[CddOut])
def list_cdd(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
) -> list[CddOut]:
    records = (
        db.query(CddRecord)
        .filter(CddRecord.tenant_id == tenant_id)
        .order_by(CddRecord.updated_at.desc())
        .limit(50)
        .all()
    )
    return [CddOut.model_validate(record) for record in records]


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    case_id: int | None = Query(default=None),
    status: str | None = Query(default=None, max_length=30),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
) -> list[TaskOut]:
    query = db.query(MatterTask).filter(MatterTask.tenant_id == tenant_id)
    if case_id is not None:
        query = query.filter(MatterTask.case_id == case_id)
    if status:
        query = query.filter(MatterTask.status == status)
    tasks = query.order_by(MatterTask.due_at.asc(), MatterTask.created_at.desc()).limit(100).all()
    return [TaskOut.model_validate(task) for task in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TaskOut:
    tenant_case(db, payload.case_id, tenant_id)
    task = MatterTask(
        tenant_id=tenant_id,
        case_id=payload.case_id,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
        priority=payload.priority,
        category=payload.category,
        owner=payload.owner,
        source=payload.source,
    )
    db.add(task)
    db.flush()
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.task.create",
        "matter_tasks",
        {"id": task.id, "case_id": task.case_id, "due_at": task.due_at.isoformat() if task.due_at else None},
    )
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task_status(
    task_id: int,
    payload: TaskStatusIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = db.query(MatterTask).filter(MatterTask.id == task_id, MatterTask.tenant_id == tenant_id).first()
    if task is None:
        raise AppError(404, "Task not found", "not_found")
    task.status = payload.status
    audit(db, tenant_id, user.id, "workflows.task.status", "matter_tasks", {"id": task_id, "status": payload.status})
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@router.post("/trust", response_model=TrustOut)
def post_trust_transaction(
    payload: TrustIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TrustOut:
    tenant_case(db, payload.case_id, tenant_id)
    tenant_client(db, payload.client_id, tenant_id)
    rows = (
        db.query(TrustTransaction)
        .filter(
            TrustTransaction.tenant_id == tenant_id,
            TrustTransaction.case_id == payload.case_id,
            TrustTransaction.client_id == payload.client_id,
        )
        .all()
    )
    balance = sum(row.amount_cents if row.kind == "receipt" else -row.amount_cents for row in rows)
    if payload.kind == "payment" and balance < payload.amount_cents:
        raise AppError(409, "Insufficient client trust balance", "trust_overdraw")
    transaction = TrustTransaction(
        tenant_id=tenant_id,
        case_id=payload.case_id,
        client_id=payload.client_id,
        kind=payload.kind,
        amount_cents=payload.amount_cents,
        reference=payload.reference,
        posted_by=payload.posted_by or user.full_name,
    )
    db.add(transaction)
    db.flush()
    balance = balance + payload.amount_cents if payload.kind == "receipt" else balance - payload.amount_cents
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.trust.post",
        "trust_transactions",
        {"id": transaction.id, "kind": payload.kind, "amount_cents": payload.amount_cents, "balance_cents": balance},
    )
    db.commit()
    db.refresh(transaction)
    return trust_out(transaction, balance)


@router.get("/trust/{case_id}", response_model=list[TrustOut])
def list_trust_transactions(
    case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
) -> list[TrustOut]:
    tenant_case(db, case_id, tenant_id)
    rows = (
        db.query(TrustTransaction)
        .filter(TrustTransaction.tenant_id == tenant_id, TrustTransaction.case_id == case_id)
        .order_by(TrustTransaction.created_at.asc())
        .all()
    )
    balance = 0
    results: list[TrustOut] = []
    for row in rows:
        balance = balance + row.amount_cents if row.kind == "receipt" else balance - row.amount_cents
        results.append(trust_out(row, balance))
    return results


@router.post("/fees/calculate", response_model=FeeOut)
def calculate_fee(
    payload: FeeIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> FeeOut:
    fees_cents = round(payload.hours * payload.hourly_rate_cents)
    subtotal = fees_cents + payload.disbursements_cents
    vat = round(subtotal * payload.vat_rate / 100)
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.fee.calculate",
        "fee_estimates",
        {"hours": payload.hours, "subtotal_cents": subtotal, "vat_cents": vat},
    )
    db.commit()
    return FeeOut(
        fees_cents=fees_cents,
        disbursements_cents=payload.disbursements_cents,
        subtotal_cents=subtotal,
        vat_cents=vat,
        total_cents=subtotal + vat,
        note="Planning estimate only. Check the current remuneration order, scope agreement and tax requirements before invoicing.",
    )


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
) -> list[TemplateOut]:
    templates = db.query(DraftTemplate).order_by(DraftTemplate.category, DraftTemplate.title).all()
    return [TemplateOut.model_validate(template) for template in templates]


@router.post("/templates/{key}/draft", response_model=TemplateDraftOut)
async def draft_from_template(
    key: str,
    payload: TemplateDraftIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> TemplateDraftOut:
    template = db.query(DraftTemplate).filter(DraftTemplate.key == key).first()
    if template is None:
        raise AppError(404, "Template not found", "not_found")
    if payload.case_id is not None:
        tenant_case(db, payload.case_id, tenant_id)
    if not rate_limiter.check(f"template:{user.id}", limit=20, window=60):
        raise AppError(429, "AI rate limit reached", "rate_limited")
    filled = template.body
    for variable in template.variables:
        value = payload.values.get(variable)
        if value:
            filled = filled.replace("{{" + variable + "}}", value)
    facts = json.dumps(payload.values, ensure_ascii=False)
    prompt = (
        "You are a Kenyan legal drafting assistant. Produce a clean first draft from the template and supplied facts. "
        "Preserve unresolved placeholders exactly. Do not invent facts, statute sections or case names. Identify any missing information.\n\n"
        f"TEMPLATE:\n{filled}\n\nSUPPLIED FACTS:\n{facts}"
    )
    try:
        draft = await stream_pico(settings.pico_lawyer_app_id, prompt, discard_chunk)
    except Exception as exc:
        raise AppError(503, "The intelligence provider is unavailable", "ai_unavailable") from exc
    notice = "AI-generated draft for review; verify all facts, law and client instructions before use."
    output = AiOutput(
        tenant_id=tenant_id,
        case_id=payload.case_id,
        preset="document",
        prompt=prompt,
        output=draft,
        sources=[{"label": f"Template: {template.title}", "url": "internal://draft-templates/" + template.key}],
        disclosure={"provider": "pico", "app_id": settings.pico_lawyer_app_id, "notice": notice},
    )
    db.add(output)
    db.flush()
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.template.draft",
        "ai_outputs",
        {"output_id": output.id, "template": template.key, "characters": len(draft)},
    )
    db.commit()
    return TemplateDraftOut(output_id=output.id, title=template.title, draft=draft, notice=notice)


@router.post("/ai/{output_id}/verify", response_model=VerifyOut)
def verify_ai_output(
    output_id: int,
    payload: VerifyIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> VerifyOut:
    output = db.query(AiOutput).filter(AiOutput.id == output_id, AiOutput.tenant_id == tenant_id).first()
    if output is None:
        raise AppError(404, "AI output not found", "not_found")
    output.verified_by = payload.verified_by
    output.verified_at = datetime.now(UTC)
    audit(
        db,
        tenant_id,
        user.id,
        "workflows.ai.verify",
        "ai_outputs",
        {"output_id": output_id, "verified_by": payload.verified_by, "note": payload.note},
    )
    db.commit()
    db.refresh(output)
    return VerifyOut.model_validate(output)


@router.get("/cpd", response_model=list[CpdOut])
def list_cpd(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user: User = Depends(get_current_user),
) -> list[CpdOut]:
    records = (
        db.query(CpdRecord)
        .filter(CpdRecord.tenant_id == tenant_id, CpdRecord.user_id == user.id)
        .order_by(CpdRecord.completed_at.desc())
        .all()
    )
    return [CpdOut.model_validate(record) for record in records]


@router.post("/cpd", response_model=CpdOut)
def add_cpd(
    payload: CpdIn,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CpdOut:
    record = CpdRecord(
        tenant_id=tenant_id,
        user_id=user.id,
        title=payload.title,
        provider=payload.provider,
        units=payload.units,
        evidence_url=payload.evidence_url,
        completed_at=payload.completed_at or datetime.now(UTC),
    )
    db.add(record)
    db.flush()
    audit(db, tenant_id, user.id, "workflows.cpd.add", "cpd_records", {"id": record.id, "units": payload.units})
    db.commit()
    db.refresh(record)
    return CpdOut.model_validate(record)
