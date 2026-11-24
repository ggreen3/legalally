# Architecture

## System shape

LegAlly is a modular monolith with a single FastAPI application serving both the JSON API and a static browser client. This keeps early deployment simple while preserving clear module boundaries for later extraction into services.

```text
Browser -> FastAPI middleware -> Routers -> Services/helpers -> SQLAlchemy -> Database
                                      |
                                      +-> AuditLog
```

## Request lifecycle

1. `app/main.py` accepts the request.
2. HTTP middleware applies rate limiting, request IDs and security headers.
3. FastAPI dependencies resolve the bearer token, active user and tenant ID.
4. A product router validates input with Pydantic and reads/writes through a SQLAlchemy session.
5. Errors are normalized by handlers in `app/errors.py`.
6. The response is JSON for `/api/*` routes or static assets for `/`.

## Tenant isolation

Every business table carries `tenant_id`. The value comes from `get_tenant_id(user)` after JWT authentication. Routers such as `app/modules/briefcase/router.py` use `tenant_record()` to verify that a record belongs to the authenticated tenant before read, update or delete operations.

Registration creates a `Tenant`, an owner `User` and a starter `Subscription` in one transaction.

## Authentication

- `bcrypt` hashes passwords.
- JWTs contain `sub`, `tenant_id`, `role`, `type`, `iat`, `exp` and a random `jti`.
- Access tokens must have `type=access`; refresh tokens must have `type=refresh`.
- `require_roles(*roles)` allows matching roles or `admin`.
- Token decode failures become structured 401 responses.

## Data model

Core entities in `app/models.py`:

- Identity and tenancy: `Tenant`, `User`, `AuditLog`, `Subscription`
- Checkbar: `CheckbarQuery`
- BriefCase: `Client`, `LegalCase`, `Document`, `TimeEntry`, `Invoice`, `InvoiceItem`, `Waitlist`
- Practice controls: `MatterTask`, `ConflictCheck`, `CddRecord`, `TrustTransaction`, `AiOutput`, `CpdRecord`
- Access and drafting content: `LegalGuide`, `DraftTemplate`
- Ecosystem: `Opportunity`, `Application`, `Resource`, `Enrollment`, `Innovation`

SQLite is the development default. Production uses the Neon `DATABASE_URL` injected by the Vercel integration (`legalally-prod-db`, Neon ID `polished-dust-98711532`) through the same SQLAlchemy interface in `app/db.py`. If `DATABASE_URL` is absent and Vercel injects `VERCEL=1`, the default is `sqlite:////tmp/legalally.db` to avoid write failures on the read-only function filesystem; that fallback is ephemeral and only a safety net. Startup calls `init_db()` and `seed_db()` so fresh environments have demo identities and the seeded guide/template library.

## Checkbar design

`app/modules/checkbar/router.py` separates answer generation from persistence and auditing.

- `local_answer()` matches common Kenyan legal topics and returns statute citations.
- `remote_answer()` calls OpenAI only when `OPENAI_API_KEY` is configured and falls back to `local_answer()` on failure.
- Each question saves the question, answer, audience, area, location, provider, citations and an audit event.
- Every response includes `DISCLAIMER`.

No API key is exposed to the browser.

## Pico realtime transport

`app/pico.py` wraps the Pico v2 WebSocket (`wss://backend.buildpicoapps.com/ask_ai_streaming_v2`). The first upstream frame is `{ appId, prompt }`; Pico replies with raw text chunks and closes normally with code `1000`.

`app/modules/checkbar/router.py` exposes `/api/checkbar/stream`. It authenticates from the `token` query parameter or first frame, validates the question with `AskRequest`, relays chunks as `{ type: "chunk", text }`, persists the final answer as provider `pico`, emits `{ type: "done", id, provider }`, and logs `checkbar.stream`. Timeouts and provider errors emit `{ type: "error", message }`; the browser falls back to the non-streaming `POST /api/checkbar/ask`.

`app/modules/ai/router.py` reuses the same transport for document drafting, case strategy and legal companion presets via three Pico app IDs from the original prototype. App IDs are configuration, not secrets. All AI calls are authenticated, rate limited, persisted as `AiOutput`, and audited. `app/modules/workflows/router.py` adds template drafting and `POST /api/workflows/ai/{output_id}/verify` so a human can record that an AI draft was reviewed.

## BriefCase design

BriefCase exposes resources for clients, matters, documents, billable time and invoices. Invoice creation calculates `total_cents` from line items and generates a unique invoice number. Status changes are constrained by a query pattern. All list and detail queries are scoped by `tenant_id`.

## Research-backed workflows

`app/modules/workflows/router.py` adds the practical layer on top of BriefCase:

- Public `LegalGuide` endpoints return researched checklists with source links and warnings.
- Conflict screening compares distinctive name tokens across tenant clients, matters and prior checks, then stores the result with an explicit scope disclaimer.
- CDD records are upserted per client and only become `complete` when the four required checks are true.
- Matter tasks carry deadlines, priority, owner and source so court dates are not left in chat threads or paper diaries.
- Trust postings compute a running balance and reject payments that would overdraw a client matter.
- Fee estimates calculate fees, disbursements and VAT with a warning to verify the current remuneration order and tax rules.
- Template drafting preserves unresolved placeholders and requires a separate human verification step.

All client-bearing endpoints derive `tenant_id` from the authenticated user and write audit events.

## Ecosystem modules

- Talent, Academy and Innovation reuse the same tenant/auth patterns.
- Public endpoints only expose active opportunities and published resources.
- Applications and enrollments are written with the opportunity/resource tenant, preserving ownership.
- Platform metrics and audit logs are owner/admin-only.

## Observability and operations

- `/api/platform/health` reports app status and database connectivity.
- Every API response includes `X-Request-ID`.
- Audit events record actions such as `briefcase.client.create` and `checkbar.ask`.
- Logs use the `legalally` logger and configured `LOG_LEVEL`.
- Docker health checks poll `/api/platform/health`.

## Testing strategy

`tests/conftest.py` points `DATABASE_URL` at an isolated temporary SQLite file before importing the app. Each test drops and recreates schema, resets the rate limiter and uses `TestClient`.

Coverage includes public endpoints, authentication lifecycle, validation errors, Checkbar answers, BriefCase tenant isolation and billing, conflict checks, task status changes, trust overdraw protection, fee estimates, template drafting with a mocked Pico transport, AI verification, Talent applications, Academy progress, Innovation review, platform metrics, audit logs and static client delivery.

## Production hardening checklist

- Set a long random `SECRET_KEY`.
- Use PostgreSQL instead of SQLite for concurrent writes.
- Put the API behind HTTPS and a reverse proxy.
- Replace the in-process rate limiter with Redis for multi-instance deployments.
- Add email verification, password reset and role invitation flows.
- Add object storage for BriefCase documents and a document versioning service.
- Add legal-review workflows before publishing Checkbar content at scale.
- Monitor audit logs, error rates and provider spend.
