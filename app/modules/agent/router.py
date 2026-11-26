from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...db import get_db
from ...deps import get_current_user
from ...errors import AppError
from ...models import AgentMessage, AgentSession, AuditLog, User
from ...pico import stream_pico
from ...security import rate_limiter

router = APIRouter()

AGENT_DISCLOSURE = (
    "The LegAlly Agent is an AI workspace. It may make mistakes and must not replace a qualified advocate. "
    "Do not submit protected client data unless you are authorised and your firm permits AI processing."
)


class AgentConfigOut(BaseModel):
    connected: bool
    mode: str
    model: str
    tools: list[str]


class SessionOut(BaseModel):
    session_key: str
    title: str
    mode: str
    status: str
    created_at: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class SessionDetailOut(BaseModel):
    session: SessionOut
    messages: list[MessageOut]


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    mode: str = Field(default="workspace", pattern="^(workspace|drafting|research)$")


class AgentPrompt(BaseModel):
    text: str = Field(min_length=3, max_length=8000)
    consent: bool = False


class AgentReply(BaseModel):
    answer: str
    provider: str
    session_key: str
    disclosure: str
    files: list[str] = Field(default_factory=list)


def service_configured() -> bool:
    return bool(settings.agent_service_url and settings.agent_service_key)


def serialize_session(session: AgentSession) -> SessionOut:
    return SessionOut(
        session_key=session.session_key,
        title=session.title,
        mode=session.mode,
        status=session.status,
        created_at=session.created_at.isoformat(),
    )


def serialize_message(message: AgentMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at.isoformat(),
    )


async def call_agent_service(session_key: str, text: str, mode: str) -> dict[str, object]:
    url = f"{settings.agent_service_url.rstrip('/')}/sessions/{session_key}/prompt"
    async with httpx.AsyncClient(timeout=settings.agent_timeout_seconds) as client:
        response = await client.post(
            url,
            headers={"x-agent-key": settings.agent_service_key or ""},
            json={"text": text, "mode": mode},
        )
    if response.status_code == 404:
        raise AppError(404, "Agent session was not found in the service", "agent_session_missing")
    if response.status_code >= 500:
        raise AppError(503, "LegAlly Agent is temporarily unavailable", "agent_unavailable")
    if response.status_code >= 400:
        raise AppError(400, "LegAlly Agent rejected that request", "agent_rejected")
    return response.json()


async def discard_chunk(_: str) -> None:
    return None


async def fallback_answer(text: str) -> str:
    try:
        answer = (await stream_pico(settings.pico_companion_app_id, text, discard_chunk)).strip()
    except RuntimeError:
        raise AppError(503, "The Studio fallback is temporarily unavailable", "studio_unavailable") from None
    if not answer:
        raise AppError(503, "The Studio fallback is temporarily unavailable", "studio_unavailable")
    return answer


@router.get("/config", response_model=AgentConfigOut)
def agent_config() -> AgentConfigOut:
    return AgentConfigOut(
        connected=service_configured(),
        mode="opencode-sdk" if service_configured() else "studio-fallback",
        model=settings.agent_model,
        tools=["workspace", "web research", "documents"] if service_configured() else ["documents"],
    )


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(
    payload: SessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionOut:
    session = AgentSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        session_key=uuid.uuid4().hex,
        title=(payload.title or "New workspace").strip(),
        mode=payload.mode,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return serialize_session(session)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    rows = (
        db.query(AgentSession)
        .filter(AgentSession.tenant_id == user.tenant_id, AgentSession.user_id == user.id)
        .order_by(AgentSession.updated_at.desc())
        .limit(20)
        .all()
    )
    return [serialize_session(row) for row in rows]


@router.get("/sessions/{session_key}", response_model=SessionDetailOut)
def get_session(
    session_key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetailOut:
    session = (
        db.query(AgentSession)
        .filter(
            AgentSession.session_key == session_key,
            AgentSession.tenant_id == user.tenant_id,
            AgentSession.user_id == user.id,
        )
        .first()
    )
    if session is None:
        raise AppError(404, "Agent session not found", "not_found")
    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.tenant_id == user.tenant_id, AgentMessage.session_id == session.id)
        .order_by(AgentMessage.created_at.asc())
        .all()
    )
    return SessionDetailOut(session=serialize_session(session), messages=[serialize_message(m) for m in messages])


@router.post("/sessions/{session_key}/prompt", response_model=AgentReply)
async def prompt_session(
    session_key: str,
    payload: AgentPrompt,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentReply:
    if not payload.consent:
        raise AppError(403, "Confirm the AI-use notice before running the Agent", "agent_consent_required")
    if not rate_limiter.check(f"agent:prompt:{user.tenant_id}", limit=15):
        raise AppError(429, "Too many Agent prompts", "rate_limited")
    session = (
        db.query(AgentSession)
        .filter(
            AgentSession.session_key == session_key,
            AgentSession.tenant_id == user.tenant_id,
            AgentSession.user_id == user.id,
        )
        .first()
    )
    if session is None:
        raise AppError(404, "Agent session not found", "not_found")

    db.add(
        AgentMessage(
            tenant_id=user.tenant_id,
            session_id=session.id,
            role="user",
            content=payload.text.strip(),
        )
    )

    if service_configured():
        result = await call_agent_service(session_key, payload.text.strip(), session.mode)
        answer = str(result.get("answer") or "").strip()
        files = [str(value) for value in (result.get("files") or [])][:30]
        provider = "opencode-sdk"
    else:
        answer = await fallback_answer(payload.text.strip())
        files = []
        provider = "studio-fallback"

    if not answer:
        raise AppError(503, "The Agent returned an empty response", "agent_empty")

    db.add(
        AgentMessage(
            tenant_id=user.tenant_id,
            session_id=session.id,
            role="assistant",
            content=answer,
            parts_json={"provider": provider, "files": files},
        )
    )
    if session.title == "New workspace":
        session.title = payload.text.strip()[:80]
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action=f"agent.prompt.{provider}",
            entity="agent_session",
            entity_id=session.id,
            metadata_json={"session_key": session_key, "mode": session.mode},
        )
    )
    db.commit()
    return AgentReply(
        answer=answer,
        provider=provider,
        session_key=session_key,
        disclosure=AGENT_DISCLOSURE,
        files=files,
    )
