# LegAlly

LegAlly is a unified legal-technology platform: **the digital infrastructure for the legal ecosystem**. This repository contains a production-oriented FastAPI backend, a static single-page web client, multi-tenant data isolation, authentication, audit logging, rate limiting, tests, CI and Docker deployment files.

## Products and ecosystem pillars

- **BriefCase** — virtual law firm infrastructure: clients, matters, documents, time entries, invoices, subscriptions and early-access waitlist.
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

Copy `.env.example` to `.env` and adjust values before deploying. Generate a strong `SECRET_KEY` and provide `OPENAI_API_KEY` only on the server; never place provider keys in the browser.

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
| `/api/auth` | Register, login, refresh token, current user |
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

The same Pico transport powers `POST /api/ai/ask` with four presets: `checkbar`, `document`, `strategy` and `companion`. BriefCase uses these for AI document drafting and case briefs. Every AI output is stored as an `AiOutput` record and can be marked reviewed through `POST /api/workflows/ai/{output_id}/verify`.

## Research-backed workflows

LegAlly now includes practical workflows derived from Kenyan legal-sector research rather than generic demo screens:

- **Access pathways:** public plain-language guides on legal-aid eligibility, e-filing deadlines, client-money controls, AML client due diligence, primary-source research and ATP/CPD planning. Each guide carries source links, an “open primary source” warning and a Kiswahili prompt where useful.
- **Conflict and client care:** name-based conflict screening against tenant records, with a clear scope disclaimer, plus a client due-diligence checklist with standard/enhanced risk tiers.
- **Matter control:** task and deadline tracking with priority, owner and source metadata.
- **Trust ledger:** receipt/payment postings with an overdraw guard and running matter balance.
- **Fees:** a transparent planning estimate with VAT and a warning to check the current remuneration order and tax rules.
- **Drafting:** template-driven Pico drafting with unresolved placeholders preserved and a human verification step.

These workflows are authenticated and tenant-isolated where they contain client data. Public guides are intentionally open because access-to-justice information should be available before sign-in.

## Vercel

`vercel.json`, `.vercelignore` and `.python-version` are included. Pushing to `main` triggers a Vercel deployment for the connected GitHub repository at `https://github.com/ggreen3/legalally`. When Vercel injects `VERCEL=1`, the default database is `sqlite:////tmp/legalally.db` so cold starts do not fail on the read-only function filesystem; this is ephemeral and is only a fallback. For persistent production data, set `DATABASE_URL` to a pooled Postgres URL (for example from the Neon/Vercel Marketplace). Startup runs `init_db()` and `seed_db()` so a fresh environment has demo users and seeded guides/templates. Required environment variables are listed in `.env.example`.

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
