from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...config import settings
from ...db import get_db
from ...deps import get_current_user, get_tenant_id
from ...errors import AppError
from ...models import AiOutput, AuditLog, User
from ...pico import stream_pico
from ...security import rate_limiter

router = APIRouter()

PRESETS = {
    "checkbar": (
        settings.pico_app_id,
        "You are The Checkbar, a Kenyan legal information assistant. Explain clearly, cite statutes where possible, and state that this is not legal advice.",
    ),
    "document": (
        settings.pico_lawyer_app_id,
        "You are a senior Kenyan commercial and litigation lawyer. Draft a professional, structured legal document using the facts supplied. Use formal legal English, numbered clauses, defined terms, and a signature block. Do not invent statute sections or case names.",
    ),
    "strategy": (
        settings.pico_lawyer_app_id,
        "You are a senior Kenyan advocate preparing a case strategy memo. Analyse issues, evidence, risks, likely outcomes and practical next steps. Be concise and must not fabricate authorities.",
    ),
    "companion": (
        settings.pico_companion_app_id,
        "You are the LegAlly Legal Companion. Identify relevant Kenyan legal principles, procedural steps and practical considerations for the supplied scenario. Do not fabricate citations.",
    ),
}


class AIRequest(BaseModel):
    preset: str = Field(default="document", pattern="^(checkbar|document|strategy|companion)$")
    prompt: str = Field(min_length=10, max_length=4000)
    context: dict[str, object] | None = None


class AIResponse(BaseModel):
    preset: str
    provider: str
    answer: str
    output_id: int | None = None


async def discard_chunk(text: str) -> None:
    return None


@router.post("/ask", response_model=AIResponse)
async def ask(
    payload: AIRequest,
    user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> AIResponse:
    if not rate_limiter.check(f"ai:{user.id}", limit=20, window=60):
        raise AppError(429, "AI rate limit reached", "rate_limited")
    app_id, system = PRESETS[payload.preset]
    context_json = json.dumps(payload.context or {}, ensure_ascii=False)
    prompt = f"{system}\n\nContext: {context_json}\nRequest: {payload.prompt}"
    try:
        answer = await stream_pico(app_id, prompt, discard_chunk)
    except Exception as exc:
        raise AppError(503, "The intelligence provider is unavailable", "ai_unavailable") from exc
    context = payload.context or {}
    raw_case_id = context.get("case_id")
    try:
        case_id = int(raw_case_id) if raw_case_id is not None else None
    except (TypeError, ValueError):
        case_id = None
    output = AiOutput(
        tenant_id=tenant_id,
        case_id=case_id,
        preset=payload.preset,
        prompt=payload.prompt,
        output=answer,
        sources=[],
        disclosure={
            "provider": "pico",
            "app_id": app_id,
            "notice": "AI-generated draft for review; verify all facts and authorities before use.",
        },
    )
    db.add(output)
    db.flush()
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user.id,
            action=f"ai.{payload.preset}",
            entity="ai_requests",
            metadata_json={
                "provider": "pico",
                "app_id": app_id,
                "characters": len(answer),
                "output_id": output.id,
            },
        )
    )
    db.commit()
    return AIResponse(preset=payload.preset, provider="pico", answer=answer, output_id=output.id)
