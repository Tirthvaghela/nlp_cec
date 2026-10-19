"""FastAPI application entry point.

Run (from backend/):  uvicorn app.main:app --reload --port 8000
API docs:             http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import deployment, model_cache
from app.config import get_settings, invite_code_problem
from app.db import ensure_indexes, get_db
from app.errors import install_error_handlers
from app.nlp.config import ENGINE_VERSION
from app.nlp.similarity import get_backend, loaded_backend
from app.ratelimit import IP_LIMITS, limiter
from app.routers import analytics, assessments, auth, enrollments, evaluations, generation, questions, results, submissions

settings = get_settings()
LAUNCHER_ENV, ADDRESS_MODE_ENV, TRANSPORT_ENV = "ANSWERWISE_LAUNCHER", "ANSWERWISE_CLIENT_ADDRESS_MODE", "ANSWERWISE_TRANSPORT"
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("answerwise")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.pilot_mode:
        # Fail closed: a pilot server only runs on a database initialised for the pilot (scripts/pilot_init_db.py).
        marker = deployment.read_marker(get_db())
        if not marker or marker.get("kind") != deployment.PILOT:
            raise RuntimeError(f"PILOT_MODE is on but database '{settings.mongodb_db}' is not marked as a pilot database "
                               "(run python -m scripts.pilot_init_db on a new, empty database).")
        if (problems := deployment.marker_problems(marker, deployment.PILOT)):  # V8: malformed marker -> refuse
            raise RuntimeError("PILOT_MODE is on but the pilot marker is invalid: " + "; ".join(problems))
        if os.environ.get(LAUNCHER_ENV) != "1":
            # V1: plain `uvicorn app.main:app` trusts X-Forwarded-For from 127.0.0.1 by default; the launcher does not.
            raise RuntimeError("PILOT_MODE requires the pilot launcher: python -m scripts.run_server (it controls "
                               "proxy-header trust and runs a single process).")
    ensure_indexes(get_db())
    if settings.preload_model:
        # Load the embedding model in the background so the first evaluation is fast
        # and the server starts immediately.
        threading.Thread(target=lambda: get_backend(settings.similarity_backend, settings.embedding_model),
                         daemon=True).start()
    yield


app = FastAPI(
    title="AnswerWise AI API",
    description="Automated descriptive answer evaluation with explainable, rubric-based feedback. "
    "AI scores are suggestions; teachers make the final decision.",
    version="1.0.0",
    lifespan=lifespan,
)
install_error_handlers(app)


@app.middleware("http")
async def auth_rate_limit(request: Request, call_next):
    """Per-IP cap on the authentication endpoints, applied before the body is parsed (malformed requests count)."""
    rule = IP_LIMITS.get(request.url.path) if request.method == "POST" else None
    if rule:
        ip = request.client.host if request.client else "unknown"
        wait = limiter.hit(f"ip:{request.url.path}:{ip}", *rule)
        if wait is not None:
            return JSONResponse({"detail": "Too many requests. Try again later.", "code": "rate_limited"},
                                status_code=429, headers={"Retry-After": str(wait)})
    return await call_next(request)


# Added after the rate-limit middleware so it wraps it: 429 responses also carry CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

for r in (auth.router, auth.users_router, assessments.router, questions.router, submissions.router,
          evaluations.router, results.router, analytics.router, enrollments.router, generation.router):
    app.include_router(r)


@app.get("/api/health", tags=["health"])
def health():
    get_db().command("ping")
    backend = loaded_backend()
    return {
        "status": "ok",
        "engine_version": ENGINE_VERSION,
        "similarity_backend": backend.name if backend else "loading",
        "model": backend.model_name if backend else None,
        "fallback_reason": backend.fallback_reason if backend else None,
        "require_review_before_publish": get_settings().require_review_before_publish,
        "pilot_mode": get_settings().pilot_mode,
        "deployment": deployment_summary(),
    }


def deployment_summary() -> dict:
    """Non-secret configuration summary for the pilot preflight (security audit F4). No credentials, host, database
    name, invite code or user data: the database appears only as a fingerprint of (name, marker instance id)."""
    s = get_settings()
    db = get_db()
    marker = deployment.read_marker(db)
    return {
        "environment": s.environment,
        "pilot_mode": s.pilot_mode,
        "require_review_before_publish": s.require_review_before_publish,
        "preload_model": s.preload_model,
        "teacher_invite_code_configured": bool(s.teacher_invite_code.strip()),
        "teacher_invite_code_strong": invite_code_problem(s.teacher_invite_code) is None,
        "database_marker": marker.get("kind") if marker else None,
        "database_marker_valid": not deployment.marker_problems(marker),
        "database_fingerprint": deployment.fingerprint(db, marker),
        # V1: how the client address is derived - "direct" (no proxy headers honoured), "trusted_proxies", or
        # "unknown" (not started by scripts/run_server.py, e.g. plain uvicorn, which trusts 127.0.0.1 by default).
        "client_address_mode": os.environ.get(ADDRESS_MODE_ENV, "unknown"),
        "trusted_proxy_count": len(s.trusted_proxy_list),
        # V12: as decided by the launcher - "tls-direct", "tls-proxy" (IT-approved proxy terminates TLS),
        # "loopback-plain" (this machine only), "plain", or "unknown" (not started by the launcher).
        "transport": os.environ.get(TRANSPORT_ENV, "unknown"),
        # Sprint 5 (A4): which model cache this process resolves (an opaque id, not the path), the revision cached
        # there and whether a variable or local directory could redirect the model. Read from disk; nothing is loaded.
        "model_cache": model_cache.identity(s.embedding_model),
    }
