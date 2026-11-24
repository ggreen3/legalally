from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import (
    CheckbarQuery,
    Client,
    CpdRecord,
    DraftTemplate,
    Innovation,
    LegalCase,
    LegalGuide,
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

        if db.query(LegalGuide).count() == 0:
            guides = [
                LegalGuide(
                    key="nlas-eligibility",
                    title="Legal aid eligibility — Kenya Legal Aid Scheme",
                    audience="client",
                    topic="legal aid",
                    summary="Check if you may qualify for government legal aid before you pay a private advocate.",
                    body={
                        "language": "English / Kiswahili",
                        "steps": [
                            "Check whether you are an indigent Kenyan or resident; the published income guide is below KSh 30,000 per month.",
                            "Confirm your matter is not expressly excluded, such as tax, debt recovery, defamation, bankruptcy or a claim by an artificial person.",
                            "Apply before a final determination is made; late applications can be refused even when the case is strong.",
                            "Attach proof of income or an affidavit explaining why you cannot prove income, plus identity and case documents.",
                            "Expect a decision within 48 hours and keep copies of everything you file.",
                        ],
                        "documents": ["National ID or refugee/IDP document", "Income proof or affidavit", "Court papers or demand letters", "Any prior legal-aid correspondence"],
                        "warning": "Eligibility rules can change; confirm the current position with the scheme or a legal-aid clinic.",
                        "swahili": "Usisubiri kesi iishe kabla ya kuomba usaidizi wa kisheria.",
                    },
                    sources=[
                        {"label": "NLAS eligibility guidance", "url": "https://nlas.go.ke/legal-aid-eligibility/"},
                        {"label": "Afrobarometer barrier data", "url": "https://www.afrobarometer.org/publication/ad1193-popular-trust-in-kenyas-courts-declines-as-barriers-to-justice-persist/"},
                    ],
                ),
                LegalGuide(
                    key="e-filing-deadlines",
                    title="E-filing and deadline control",
                    audience="advocate",
                    topic="procedure",
                    summary="Practical controls for filing day and end-of-day deadlines in Kenya.",
                    body={
                        "steps": [
                            "Record the deadline in EAT and display it in matter tasks with an owner.",
                            "Check the official e-filing platform and the relevant court cause list before drafting.",
                            "File early; nationwide e-filing deadlines run to 23:59:59 EAT and systems can be unavailable near midnight.",
                            "Save the filing receipt and proof of service against the matter.",
                            "Escalate any missed step to the responsible advocate the same day.",
                        ],
                        "warning": "LegAlly is not a court filing system. Verify the current registry rules and platform status.",
                    },
                    sources=[
                        {"label": "Kenya Judiciary Practice Directions 2020", "url": "https://www.kenyalaw.org/kl/index.php?id=10211"},
                        {"label": "Supreme Court filing guidelines", "url": "https://supremecourt.judiciary.go.ke/guidelines-for-filing-of-documents/"},
                    ],
                ),
                LegalGuide(
                    key="client-money-controls",
                    title="Client money and trust ledger controls",
                    audience="advocate",
                    topic="compliance",
                    summary="Keep client funds identifiable, reconcilable and separate from office money.",
                    body={
                        "steps": [
                            "Record every receipt and payment against the client and matter in the trust ledger.",
                            "Never allow a matter balance to go negative by posting a payment before a receipt.",
                            "Reconcile the ledger to bank statements at least monthly.",
                            "Preserve client authorisation for each payment and link it to the ledger entry.",
                            "Escalate any discrepancy immediately to the responsible advocate.",
                        ],
                        "warning": "This is an internal control aid, not a substitute for the Advocates (Accounts) Rules or professional advice.",
                    },
                    sources=[{"label": "Advocates (Accounts) Rules", "url": "https://new.kenyalaw.org/akn/ke/act/ln/1966/137/eng@2022-12-31"}],
                ),
                LegalGuide(
                    key="aml-client-due-diligence",
                    title="Client due diligence checklist",
                    audience="advocate",
                    topic="compliance",
                    summary="A working checklist for identification, beneficial ownership and risk review.",
                    body={
                        "steps": [
                            "Identify the client and verify identity documents before substantial work begins.",
                            "Identify beneficial owners for companies and other legal arrangements.",
                            "Understand the purpose and nature of the proposed engagement.",
                            "Assign standard, enhanced or reduced risk and record the reason.",
                            "Re-review when circumstances change and keep the dated record.",
                        ],
                        "warning": "The LSK AML/CFT/CPF Guidelines 2025 are the governing practice source; confirm current requirements.",
                    },
                    sources=[{"label": "LSK AML/CFT/CPF Guidelines 2025", "url": "https://lsk.or.ke/wp-content/uploads/2026/01/The-Legal-Sector-Guidelines-on-AML-CFT-CPF.pdf"}],
                ),
                LegalGuide(
                    key="student-research-workflow",
                    title="Primary-source research workbook",
                    audience="student",
                    topic="research",
                    summary="Turn a legal question into a verified memo using Kenya Law primary sources.",
                    body={
                        "steps": [
                            "Write the issue in one sentence and list the keywords and possible causes of action.",
                            "Find the governing statute or Constitution provision and record its commencement and amendments.",
                            "Filter judgments by court, date and subject, then read the full text rather than relying on headnotes.",
                            "Pinpoint the exact paragraph that supports each proposition.",
                            "Mark the memo verified only after opening the primary source and saving a stable link.",
                        ],
                        "warning": "AI summaries are a starting point. Never cite an unseen case or unchecked provision.",
                    },
                    sources=[
                        {"label": "Kenya Law", "url": "https://kenyalaw.org/"},
                        {"label": "Kenya Law help and data notes", "url": "https://help.kenyalaw.org/llms.txt"},
                    ],
                ),
                LegalGuide(
                    key="career-atp-cle",
                    title="ATP and continuous learning plan",
                    audience="student",
                    topic="career",
                    summary="Plan the Advocates Training Programme and capture CPD evidence in one place.",
                    body={
                        "steps": [
                            "Confirm current admission rules with KSL; the ATP is 18 months: 12 months coursework and 6 months pupillage.",
                            "Track the nine units and keep evidence of assessments and pupillage work.",
                            "Add completed CLE or CPD sessions with provider, date, units and evidence link.",
                            "Review gaps monthly before renewal or bar requirements become urgent.",
                        ],
                        "warning": "Draft regulations are not law; rely on published KSL and CLE notices.",
                    },
                    sources=[
                        {"label": "Kenya School of Law ATP", "url": "https://ksl.ac.ke/advocates-training-program"},
                        {"label": "Continuing Legal Education", "url": "https://cle.or.ke/bar-examination"},
                    ],
                ),
            ]
            db.add_all(guides)

        if db.query(DraftTemplate).count() == 0:
            templates = [
                DraftTemplate(
                    key="intake-note",
                    title="Client intake note",
                    category="intake",
                    body="Client: {{client_name}}\nMatter: {{matter}}\nDate: {{date}}\n\nIssue:\nObjective:\nKey facts:\nDocuments received:\nUrgent dates:\nConflicts checked:\nNext steps:",
                    variables=["client_name", "matter", "date"],
                ),
                DraftTemplate(
                    key="conflict-note",
                    title="Conflict check note",
                    category="conflict",
                    body="Client: {{client_name}}\nAdverse parties: {{adverse_parties}}\nSearch performed by: {{reviewer}}\nResult: {{result}}\nReason: {{reason}}\nClearance:",
                    variables=["client_name", "adverse_parties", "reviewer", "result", "reason"],
                ),
                DraftTemplate(
                    key="engagement-letter",
                    title="Engagement letter skeleton",
                    category="client-care",
                    body="To: {{client_name}}\nRe: {{matter}}\n\n1. Scope of work\n2. Fees and billing basis\n3. Client responsibilities\n4. Communication and reporting\n5. Confidentiality and data\n6. Termination\n7. Acceptance",
                    variables=["client_name", "matter"],
                ),
                DraftTemplate(
                    key="case-brief",
                    title="Case brief",
                    category="litigation",
                    body="Matter: {{matter}}\nCourt/file number: {{file_number}}\n\nIssue:\nRelevant law:\nAuthorities verified:\nFacts in support:\nFacts against:\nOrders sought:\nRisks:\nNext deadline:",
                    variables=["matter", "file_number"],
                ),
                DraftTemplate(
                    key="research-memo",
                    title="Research memo",
                    category="research",
                    body="Question: {{question}}\nJurisdiction: Kenya\n\nShort answer:\nAuthorities:\nApplication:\nCounter-view:\nConclusion:\nSource check date: {{date}}",
                    variables=["question", "date"],
                ),
                DraftTemplate(
                    key="demand-letter",
                    title="Demand letter skeleton",
                    category="negotiation",
                    body="To: {{recipient}}\nRe: {{matter}}\n\nFacts:\nLegal basis:\nWhat is required:\nDeadline:\nConsequences if unresolved:\nWithout prejudice where appropriate:",
                    variables=["recipient", "matter"],
                ),
                DraftTemplate(
                    key="nlas-checklist",
                    title="Legal-aid application checklist",
                    category="access",
                    body="Applicant: {{client_name}}\nIncome guide: below KSh 30,000 per month\nProof of income or affidavit: [ ]\nIdentity document: [ ]\nCourt papers: [ ]\nExcluded matter check: [ ]\nFiled before final determination: [ ]\nDecision expected within 48 hours",
                    variables=["client_name"],
                ),
                DraftTemplate(
                    key="witness-statement",
                    title="Witness statement skeleton",
                    category="litigation",
                    body="Witness: {{witness}}\nMatter: {{matter}}\n\n1. Identity and capacity\n2. Knowledge of facts\n3. Sequence of events\n4. Documents referred to\n5. Truth statement\n6. Signature and date",
                    variables=["witness", "matter"],
                ),
            ]
            db.add_all(templates)

        if db.query(CpdRecord).count() == 0:
            demo_admin = db.query(User).filter(User.email == "admin@legalally.co.ke").first()
            if demo_admin is not None:
                db.add(
                    CpdRecord(
                        tenant_id=tenant.id,
                        user_id=demo_admin.id,
                        title="Legal practice and professional conduct",
                        provider="Demonstration provider",
                        units=2,
                    )
                )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()
