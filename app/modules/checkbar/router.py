from __future__ import annotations

import json
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...db import SessionLocal, get_db
from ...deps import get_current_user, get_tenant_id
from ...errors import AppError
from ...models import AuditLog, CheckbarQuery, User
from ...pico import stream_pico
from ...security import decode_token, rate_limiter

router = APIRouter()

DISCLAIMER = (
    "This information is general legal information, not legal advice. "
    "Verify the law and consult a qualified advocate before acting."
)


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    user_type: str = Field(default="General public", max_length=50)
    area_of_law: str = Field(default="Understanding a legal concept or procedure", max_length=120)
    location: str = Field(default="Kenya", max_length=120)


class Citation(BaseModel):
    source: str
    section: str | None = None


class AskResponse(BaseModel):
    id: int
    answer: str
    citations: list[Citation]
    provider: str
    disclaimer: str


class QueryOut(BaseModel):
    id: int
    question: str
    user_type: str
    area_of_law: str
    location: str
    answer: str
    citations: list[dict]
    provider: str
    created_at: datetime

    model_config = {"from_attributes": True}


def local_answer(question: str, user_type: str, area_of_law: str, location: str) -> tuple[str, list[dict]]:
    q = question.lower()
    if "civil" in q and "criminal" in q:
        return (
            "Civil cases resolve private disputes such as contracts or property between parties, usually "
            "with compensation or an order as the outcome. Criminal cases are brought by the state against "
            "a person accused of an offence and can result in punishment such as a fine or imprisonment.",
            [{"source": "Constitution of Kenya", "section": "Article 50 (fair hearing)"}],
        )
    if "contract" in q or "agreement" in q:
        return (
            "A binding contract generally needs an offer, acceptance, consideration and an intention to "
            "create legal relations. Keep the written terms, payment records and any variations, and check "
            "whether the agreement has a dispute-resolution clause.",
            [{"source": "Kenya Contract Act", "section": "Sections 2-4"}],
        )
    if "landlord" in q or "rent" in q or "tenancy" in q:
        return (
            "Residential tenancy in Kenya is governed by the Rent Restriction Act and the landlord and "
            "tenant relationship. Check the written tenancy agreement, notice periods and rent control "
            "provisions before withholding rent or moving out.",
            [{"source": "Rent Restriction Act (Cap. 296)", "section": "Sections 5 and 7"}],
        )
    if "employment" in q or "termination" in q or "dismissal" in q:
        return (
            "Termination of employment must follow the Employment Act: a valid reason, fair procedure, "
            "notice and payment of terminal benefits. Keep written records and raise a grievance with the "
            "labour officer if the process was unfair.",
            [{"source": "Employment Act 2007", "section": "Sections 35-45"}],
        )
    if "bail" in q or "arrest" in q:
        return (
            "A person arrested has rights including being informed of the reason, legal representation and "
            "being brought to court within the time allowed by law. Bail is at the court's discretion and "
            "depends on the offence and flight risk.",
            [{"source": "Constitution of Kenya", "section": "Article 49 and Article 50"}],
        )
    if "will" in q or "succession" in q or "inheritance" in q:
        return (
            "Succession in Kenya may be testate (with a will) or intestate (without one). For intestate "
            "estates, the Law of Succession Act sets out the order of beneficiaries, and a grant of "
            "representation is usually needed before distributing the estate.",
            [{"source": "Law of Succession Act (Cap. 160)", "section": "Section 29"}],
        )
    if "court" in q or "sue" in q or "file a case" in q:
        return (
            "Identify the correct court by jurisdiction and value of the claim, draft a plaint or petition "
            "with supporting documents, pay the filing fees and serve the other party. Limitation periods "
            "can bar late claims, so act promptly.",
            [{"source": "Civil Procedure Act", "section": "Order 3 and Limitation of Actions Act"}],
        )
    audience = {
        "Law student": "As a law student, start from the primary legislation and leading authorities.",
        "Legal professional": "As a legal professional, verify against current statutes and recent decisions.",
    }.get(user_type, "Start with the relevant statute and keep a record of the steps you take.")
    return (
        f"The Checkbar could not find a specific rule for this question in its local knowledge base. "
        f"{audience} Provide more detail about {area_of_law or 'the area of law'} and {location or 'your location'} "
        "to get a more focused answer, and confirm the position with a qualified advocate.",
        [],
    )


async def remote_answer(question: str, user_type: str, area_of_law: str, location: str) -> tuple[str, list[dict]]:
    if not settings.openai_api_key:
        return local_answer(question, user_type, area_of_law, location)
    system = (
        "You are The Checkbar, a Kenyan legal information assistant. Give clear, practical, "
        "easy-to-understand information and next steps. Always state that this is not legal advice. "
        "Cite statutes or sections where possible. Do not invent case names or provisions."
    )
    prompt = (
        f"User type: {user_type}\nArea of law: {area_of_law}\nLocation: {location}\n"
        f"Question: {question}\n\nProvide general information and next steps with citations."
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
            )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return str(content), [{"source": "Model-generated summary", "section": "Verify with primary law"}]
    except (httpx.HTTPError, KeyError, IndexError, TypeError):
        return local_answer(question, user_type, area_of_law, location)


@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    request_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> AskResponse:
    if not rate_limiter.check(f"checkbar:{request_user.id}", limit=30, window=60):
        raise AppError(429, "Checkbar rate limit reached", "rate_limited")
    answer, citations = await remote_answer(
        payload.question, payload.user_type, payload.area_of_law, payload.location
    )
    provider = "openai" if settings.openai_api_key else "local"
    record = CheckbarQuery(
        tenant_id=tenant_id,
        user_id=request_user.id,
        question=payload.question,
        user_type=payload.user_type,
        area_of_law=payload.area_of_law,
        location=payload.location,
        answer=answer,
        citations=citations,
        provider=provider,
    )
    db.add(record)
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=request_user.id,
            action="checkbar.ask",
            entity="checkbar_queries",
            metadata_json={"provider": provider},
        )
    )
    db.commit()
    db.refresh(record)
    return AskResponse(
        id=record.id,
        answer=answer,
        citations=[Citation.model_validate(c) for c in citations],
        provider=provider,
        disclaimer=DISCLAIMER,
    )


@router.get("/history", response_model=list[QueryOut])
def history(
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[QueryOut]:
    rows = (
        db.query(CheckbarQuery)
        .filter(CheckbarQuery.tenant_id == tenant_id)
        .order_by(CheckbarQuery.created_at.desc())
        .limit(50)
        .all()
    )
    return [QueryOut.model_validate(row) for row in rows]


def build_pico_prompt(payload: AskRequest) -> str:
    prompt = (
        "You are The Checkbar, a Kenyan legal information assistant. Give clear, practical, "
        "easy-to-understand information and concrete next steps. Cite relevant Kenyan statutes or "
        "sections where possible. Do not invent case names or provisions. Always state that the "
        "response is general information and not legal advice.\n"
        f"User type: {payload.user_type}\n"
        f"Area of law: {payload.area_of_law}\n"
        f"Location: {payload.location}\n"
        f"Question: {payload.question}\n"
    )
    return prompt[: settings.pico_max_prompt_chars]


def resolve_socket_user(token: str) -> User:
    payload = decode_token(token, "access")
    user_id = int(payload.get("sub", ""))
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise ValueError("inactive user")
        db.expunge(user)
        return user
    finally:
        db.close()


async def socket_error(websocket: WebSocket, message: str, code: int = 1000) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:
        pass
    try:
        await websocket.close(code=code)
    except Exception:
        pass


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    await websocket.accept()
    db: Session | None = None
    try:
        raw_text = await websocket.receive_text()
        raw = json.loads(raw_text)
        if not isinstance(raw, dict):
            await socket_error(websocket, "Invalid stream payload")
            return
        token = websocket.query_params.get("token") or raw.get("token")
        if not token:
            await socket_error(websocket, "Authentication required", 4401)
            return
        try:
            user = resolve_socket_user(str(token))
        except Exception:
            await socket_error(websocket, "Authentication required", 4401)
            return
        if not rate_limiter.check(f"checkbar-stream:{user.id}", limit=30, window=60):
            await socket_error(websocket, "Checkbar rate limit reached", 4429)
            return
        ask = AskRequest.model_validate(raw)
        prompt = build_pico_prompt(ask)

        async def forward_chunk(text: str) -> None:
            await websocket.send_json({"type": "chunk", "text": text})

        answer = await stream_pico(settings.pico_app_id, prompt, forward_chunk)
        db = SessionLocal()
        record = CheckbarQuery(
            tenant_id=user.tenant_id,
            user_id=user.id,
            question=ask.question,
            user_type=ask.user_type,
            area_of_law=ask.area_of_law,
            location=ask.location,
            answer=answer,
            citations=[],
            provider="pico",
        )
        db.add(record)
        db.add(
            AuditLog(
                tenant_id=user.tenant_id,
                user_id=user.id,
                action="checkbar.stream",
                entity="checkbar_queries",
                metadata_json={"provider": "pico", "characters": len(answer)},
            )
        )
        db.commit()
        db.refresh(record)
        await websocket.send_json({"type": "done", "id": record.id, "provider": "pico"})
    except WebSocketDisconnect:
        return
    except TimeoutError:
        await socket_error(websocket, "The intelligence stream timed out")
    except Exception:
        await socket_error(websocket, "The intelligence stream is unavailable")
    finally:
        if db is not None:
            db.close()
        try:
            await websocket.close()
        except Exception:
            pass
