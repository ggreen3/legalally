from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401
from .config import settings
from .db import init_db
from .errors import register_error_handlers
from .modules import (
    agent,
    ai,
    auth,
    briefcase,
    checkbar,
    education,
    innovation,
    platform,
    spaces,
    talent,
    workflows,
)
from .security import rate_limiter
from .seed import seed_db

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("legalally")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_db()
    logger.info("%s started in %s mode", settings.app_name, settings.environment)
    yield
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Digital infrastructure for the legal ecosystem",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    if request.url.path.startswith("/api/") and not rate_limiter.check(
        f"{request.client.host if request.client else 'unknown'}:{request.url.path}"
    ):
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "rate_limited", "message": "Too many requests"}},
            headers={"X-Request-ID": request_id},
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(checkbar.router, prefix="/api/checkbar", tags=["checkbar"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(briefcase.router, prefix="/api/briefcase", tags=["briefcase"])
app.include_router(talent.router, prefix="/api/talent", tags=["talent"])
app.include_router(education.router, prefix="/api/education", tags=["education"])
app.include_router(innovation.router, prefix="/api/innovation", tags=["innovation"])
app.include_router(platform.router, prefix="/api/platform", tags=["platform"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(spaces.router, prefix="/api/spaces", tags=["spaces"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])

static_dir = Path(__file__).parent / "static"


@app.get("/waitlist", include_in_schema=False)
def waitlist_page() -> FileResponse:
    return FileResponse(static_dir / "waitlist.html")


app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
