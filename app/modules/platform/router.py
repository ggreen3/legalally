from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ... import models
from ...config import settings
from ...db import engine, get_db
from ...deps import get_tenant_id, require_roles
from ...models import AuditLog, User

router = APIRouter()

PILLARS = [
    {
        "name": "Legal Practice Management",
        "description": "Virtual law firm infrastructure, clients, cases, documents, billing and workflows.",
        "product": "BriefCase",
        "status": "available",
    },
    {
        "name": "Legal AI and Automation",
        "description": "AI-assisted research, drafting, contract review and legal information assistance.",
        "product": "The Checkbar",
        "status": "available",
    },
    {
        "name": "Access to Justice",
        "description": "Plain-language guidance and affordable self-help routes into the legal system.",
        "product": "The Checkbar",
        "status": "available",
    },
    {
        "name": "Legal Talent and Opportunities",
        "description": "Marketplace connecting advocates, students and firms to internships and roles.",
        "product": "Talent",
        "status": "available",
    },
    {
        "name": "Legal Education and Professional Development",
        "description": "Learning resources, CPD and practical training for legal professionals.",
        "product": "Academy",
        "status": "available",
    },
    {
        "name": "Legal Business and Innovation",
        "description": "Innovation submissions, IP support and infrastructure for legal entrepreneurship.",
        "product": "Innovation",
        "status": "available",
    },
]


@router.get("/health")
def health() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "app": settings.app_name,
        "version": "0.1.0",
        "environment": settings.environment,
        "database": database,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/pillars")
def pillars() -> list[dict]:
    return PILLARS


@router.get("/metrics")
def metrics(
    user: User = Depends(require_roles("owner", "admin")),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> dict:
    counts = {}
    for name in (
        "clients",
        "cases",
        "documents",
        "invoices",
        "checkbar_queries",
        "opportunities",
        "applications",
        "resources",
        "innovations",
    ):
        model = getattr(models, {
            "clients": "Client",
            "cases": "LegalCase",
            "documents": "Document",
            "invoices": "Invoice",
            "checkbar_queries": "CheckbarQuery",
            "opportunities": "Opportunity",
            "applications": "Application",
            "resources": "Resource",
            "innovations": "Innovation",
        }[name])
        counts[name] = db.query(func.count(model.id)).filter(model.tenant_id == tenant_id).scalar()
    return {"tenant_id": tenant_id, "counts": counts}


@router.get("/audit-logs")
def audit_logs(tenant_id: int = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity": row.entity,
            "entity_id": row.entity_id,
            "user_id": row.user_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
