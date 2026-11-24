from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import (
    CheckbarQuery,
    Client,
    Innovation,
    LegalCase,
    Opportunity,
    Resource,
    Subscription,
    Tenant,
    User,
    Waitlist,
)
from .security import hash_password


def seed_db() -> None:
    init_db()
    db: Session = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == "legalally-demo").first()
        if tenant is None:
            tenant = Tenant(name="LegAlly Demo", slug="legalally-demo", tier="firm", is_active=True)
            db.add(tenant)
            db.flush()

        if db.query(User).filter(User.email == "admin@legalally.co.ke").first() is None:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email="admin@legalally.co.ke",
                    full_name="LegAlly Administrator",
                    hashed_password=hash_password("Admin123!"),
                    role="admin",
                    is_active=True,
                    is_verified=True,
                )
            )

        if db.query(User).filter(User.email == "advocate@legalally.co.ke").first() is None:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email="advocate@legalally.co.ke",
                    full_name="Demo Advocate",
                    hashed_password=hash_password("Advocate123!"),
                    role="advocate",
                    is_active=True,
                    is_verified=True,
                )
            )

        if db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first() is None:
            db.add(
                Subscription(
                    tenant_id=tenant.id,
                    tier="firm",
                    status="active",
                    monthly_price_cents=1000000,
                    starts_at=datetime.now(UTC),
                    ends_at=datetime.now(UTC) + timedelta(days=365),
                )
            )

        client = db.query(Client).filter(Client.tenant_id == tenant.id).first()
        if client is None:
            client = Client(
                tenant_id=tenant.id,
                name="Demo Client",
                email="client@example.com",
                phone="+254700000000",
            )
            db.add(client)
            db.flush()

        if db.query(LegalCase).filter(LegalCase.tenant_id == tenant.id).first() is None:
            db.add(
                LegalCase(
                    tenant_id=tenant.id,
                    client_id=client.id,
                    title="Contract review engagement",
                    case_number="LA-2026-001",
                    category="commercial",
                    status="open",
                    description="Draft and review a services agreement.",
                )
            )

        if db.query(Opportunity).filter(Opportunity.tenant_id == tenant.id).first() is None:
            db.add(
                Opportunity(
                    tenant_id=tenant.id,
                    title="Legal Tech Innovation Showcase",
                    organization="LegAlly",
                    category="showcase",
                    location="Nairobi, Kenya",
                    description="Present LegAlly to an innovation panel.",
                )
            )

        if db.query(Resource).filter(Resource.tenant_id == tenant.id).first() is None:
            db.add(
                Resource(
                    tenant_id=tenant.id,
                    title="Understanding Kenya's legal system",
                    category="guide",
                    level="beginner",
                    body="An introduction to courts, statutes and procedure in Kenya.",
                    is_published=True,
                )
            )

        if db.query(Innovation).filter(Innovation.tenant_id == tenant.id).first() is None:
            db.add(
                Innovation(
                    tenant_id=tenant.id,
                    title="BriefCase",
                    description="Virtual law firm infrastructure for remote legal practice.",
                    sector="legal tech",
                    stage="mvp",
                    submitted_by="LegAlly",
                )
            )

        if db.query(CheckbarQuery).count() == 0:
            db.add(
                CheckbarQuery(
                    tenant_id=tenant.id,
                    question="What is the difference between civil and criminal cases?",
                    user_type="General public",
                    area_of_law="Understanding a legal concept or procedure",
                    location="Kenya",
                    answer="Civil cases resolve disputes between parties; criminal cases involve the state prosecuting an alleged offence.",
                    citations=[{"source": "Kenya Constitution", "section": "Article 50"}],
                    provider="local",
                )
            )

        if db.query(Waitlist).count() == 0:
            db.add(Waitlist(name="Demo User", email="demo@example.com", role="advocate"))

        db.commit()
        print("Seed complete: admin@legalally.co.ke / Admin123!")
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()
