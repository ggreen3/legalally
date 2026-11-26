# LegAlly

LegAlly is a unified legal-technology platform: **the digital infrastructure for the legal ecosystem**. This repository contains a production-oriented FastAPI backend, a static single-page web client, multi-tenant data isolation, authentication, audit logging, rate limiting, tests, CI and Docker deployment files.

## Products and ecosystem pillars

- **BriefCase** — virtual law firm infrastructure: clients, matters, documents, time entries, invoices, subscriptions, firm command center, official court registry links, cause-list task preparation and early-access waitlist.
- **The Checkbar** — Kenyan legal information assistant with a local rule-based knowledge base and optional OpenAI provider.
- **Talent** — opportunities and applications connecting advocates, students and firms.
- **Academy** — legal education resources, enrollments and progress tracking.
- **Innovation** — legal-business and legal-tech idea submissions with review workflow.
- **Platform** — health checks, pillars catalogue, tenant metrics and audit logs.

## Requirements

- Python 3.11 or newer
- Docker and Docker Compose for containerized deployment

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Seeded admin credentials:

```text
admin@legalally.co.ke / Admin123!
advocate@legalally.co.ke / Advocate123!
```

Copy `.env.example` to `.env` and adjust values before deploying. Generate a strong `SECRET_KEY` and provide `OPENAI_API_KEY` only on the server; never place provider keys in the browser. Google sign-in is optional: set `GOOGLE_CLIENT_ID` to a Google OAuth web client ID, then authorize the local and production origins in Google Cloud. The browser receives only the public client ID; the backend verifies Google ID tokens and issues the normal LegAlly JWTs.

## Tests and lint

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```

CI runs the same lint and test commands on every push and pull request.

## Docker deployment

```powershell
docker compose up --build -d
docker compose logs -f app
```

The application serves the web client and API on port `8000`. SQLite data is persisted in the `legalally-data` volume at `/data/legalally.db`.

## API overview

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

| Prefix | Purpose |
| --- | --- |
| `/api/auth` | Register, login, Google ID-token sign-in, refresh token, current user |
| `/api/checkbar` | Ask legal information questions, stream answers and view history |
| `/api/ai` | Pico-powered document drafting, case strategy and legal companion |
| `/api/briefcase` | Practice management and billing |
| `/api/talent` | Opportunities and applications |
| `/api/education` | Learning resources and enrollments |
| `/api/innovation` | Innovation submissions and review |
| `/api/workflows` | Research-backed guides, conflict checks, CDD, deadlines, trust ledger, fee estimates, templates and AI verification |
| `/api/platform` | Health, pillars, metrics and audit logs |

All protected endpoints use `Authorization: Bearer <access_token>`. Tenant boundaries are derived from the authenticated user, not from request payloads.

## Security notes

- Passwords are hashed with bcrypt.
- Access and refresh tokens are JWTs with short-lived access tokens.
- The global API rate limiter and per-endpoint login/Checkbar limits reduce abuse.
- Client requests receive standard security headers and request IDs.
- Errors return a consistent `{ "error": { "code", "message" } }` shape.
- The Checkbar always returns a disclaimer that its output is general information, not legal advice.

## Pico intelligence

The Checkbar streams answers from the original Pico AI WebSocket used in the LegAlly prototype:

```text
wss://backend.buildpicoapps.com/ask_ai_streaming_v2
```

The browser opens an authenticated WebSocket to `ws(s)://<host>/api/checkbar/stream`, sends the question payload, and receives `chunk`, `done` and `error` events. The backend proxies Pico, enforces auth and rate limits, persists the full answer, and writes an audit event. If the stream fails, the client falls back to `POST /api/checkbar/ask`.

The same Pico transport powers `POST /api/ai/ask` with four presets: `checkbar`, `document`, `strategy` and `companion`. BriefCase uses these for AI document drafting and case briefs; LegAlly Studio uses the same transport behind a white-labelled workspace interface with provider and model labels hidden. Every AI output is stored as an `AiOutput` record and can be marked reviewed through `POST /api/workflows/ai/{output_id}/verify`.

## Lawful use of OpenCode and AI models

- OpenCode's source is MIT licensed, so commercial use and modification are allowed when the copyright and permission notice are retained.
- `@opencode/sdk` embeds a full OpenCode host and needs a Bun/Node runtime. The current Vercel Python app cannot host it directly; a separate self-hosted Node/Bun service would be required for a true embedded OpenCode feature.
- Free-tier chat models, including Big Pickle, are restricted to OpenCode clients. Calling them directly from LegAlly's Python backend is not permitted. Even through OpenCode, some free models may use collected data to improve the model, so free models must stay behind explicit informed consent and must not receive confidential client data by default.
- OpenCode and Anomaly trademarks, logos and colours may not be renamed, recoloured or presented as LegAlly's own, and may not imply endorsement. If LegAlly later embeds OpenCode, describe it as "LegAlly Studio, built with OpenCode", link to `https://opencode.ai`, and use unmodified official badge assets.
- The current site makes no claim that Studio is OpenCode or Big Pickle. Studio shows an AI-use notice, requires confirmation before each run, and warns users not to submit protected client data without authorisation.

## LegAlly Agent

`app/modules/agent/router.py` adds an authenticated, tenant-isolated Agent workspace to the site. Users create sessions, send prompts, see thread history, and receive a disclosure. Without the service env vars, the platform clearly reports "Studio fallback" and uses the existing companion transport; it never pretends the OpenCode service is connected.

`agent-service/` is the separate Bun host that makes the embedded OpenCode feature real:

```bash
cd agent-service
bun install
cp .env.example .env
bun run dev
```

Set `AGENT_SERVICE_KEY` to a long random value and set `OPENCODE_MODEL` plus the matching provider API key, for example `ANTHROPIC_API_KEY`. `OPENCODE_DISABLE_FREE_MODELS=1` is set by default; free models must stay disabled for confidential legal work unless informed consent is captured. `ENABLE_BROWSER_TOOLS=1` adds a Playwright MCP browser server for public-web research only.

Deploy `agent-service/` as a long-running Bun container, then set these on the main FastAPI app:

```text
AGENT_SERVICE_URL=https://your-agent-service.example
AGENT_SERVICE_KEY=same-long-random-value
AGENT_MODEL=anthropic/claude-sonnet-5-5
AGENT_TIMEOUT_SECONDS=90
```

The service creates one workspace per tenant/session, writes an `opencode.jsonc` permission policy, and uses `@opencode/sdk` in-process. Shell execution, subagents, external directories, code mode and permission prompts are denied; workspace reads/writes, web fetch/web search are allowed, and browser tools are optional. Users interact through the site exactly as with other workspace features; no OpenCode CLI is required.

## Workspace marketplace

`app/modules/spaces/router.py` powers the "Spaces" section: public search/filtering for serviced offices, shared team rooms, shortlets, leases and boardrooms, plus authenticated enquiry tracking and owner listings. Listings and enquiries are tenant-aware, rate-limited and audited. Seed listings are inserted idempotently by `app/seed.py` so a fresh database has a useful marketplace immediately.

## Waitlist

`https://legalally-ivory.vercel.app/waitlist` is the public early-access page for the BriefCase waitlist. Registrations are stored in the `waitlist` table and are de-duplicated by normalised email. Admin users can review responses at `GET /api/briefcase/waitlist` and download `legalally-waitlist.csv` from `GET /api/briefcase/waitlist/export`; the signed-in BriefCase view also shows the responses and download button.

## Research-backed workflows

LegAlly now includes practical workflows derived from Kenyan legal-sector research rather than generic demo screens:

- **Access pathways:** public plain-language guides on legal-aid eligibility, e-filing deadlines, client-money controls, AML client due diligence, primary-source research and ATP/CPD planning. Each guide carries source links, an “open primary source” warning and a Kiswahili prompt where useful.
- **Conflict and client care:** name-based conflict screening against tenant records, with a clear scope disclaimer, plus a client due-diligence checklist with standard/enhanced risk tiers.
- **Matter control:** task and deadline tracking with priority, owner and source metadata.
- **Court registry:** official links to Kenya's eFiling and Cause List portals with matter-linked checklist tasks; LegAlly prepares the work, while filing and registry searches are completed on the official portals.
- **Trust ledger:** receipt/payment postings with an overdraw guard and running matter balance.
- **Fees:** a transparent planning estimate with VAT and a warning to check the current remuneration order and tax rules.
- **Drafting:** template-driven Pico drafting with unresolved placeholders preserved and a human verification step.

These workflows are authenticated and tenant-isolated where they contain client data. Public guides are intentionally open because access-to-justice information should be available before sign-in.

## Vercel

`vercel.json`, `.vercelignore` and `.python-version` are included. Pushing to `main` triggers a Vercel deployment for the connected GitHub repository at `https://github.com/ggreen3/legalally`. Production uses the `DATABASE_URL` injected by the Neon integration on the Vercel project (`legalally-prod-db`, Neon ID `polished-dust-98711532`) for persistent pooled Postgres data. If `DATABASE_URL` is absent and Vercel injects `VERCEL=1`, the default is `sqlite:////tmp/legalally.db` so cold starts do not fail on the read-only function filesystem; that fallback is ephemeral and is only for local preview smoke tests. Startup runs `init_db()` and `seed_db()` so a fresh environment has demo users and seeded guides/templates. Required environment variables are listed in `.env.example`.

## Project layout

```text
app/
  main.py                 FastAPI app, middleware, router wiring, static client
  config.py               Environment-backed settings
  db.py                   SQLAlchemy engine and sessions
  models.py               Multi-tenant data models
  security.py             Password hashing, JWTs, rate limiter
  deps.py                 Authentication and tenant dependencies
  errors.py               Error handlers
  seed.py                 Demo data seeder
  modules/                Product routers
  modules/workflows/      Research-backed practice and access workflows
  static/                 Web client
tests/                    API tests
.github/workflows/ci.yml  Continuous integration
Dockerfile                Container image
docker-compose.yml        Local/production Compose stack
```

See `ARCHITECTURE.md` for design decisions and extension guidance.
