"""Level 1 FastAPI application for ORB Platform."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import get_settings
from integrations.claude_client import ping_claude
from integrations.openai_client import ask_gpt_mini
from platform.api.routes import agents, assistant, auth, content, identity, trading, webhooks, wholesale
from platform.database.connection import SupabaseClient

settings = get_settings()

app = FastAPI(
    title="ORB Platform",
    version="0.1.0",
    description="Level 1 foundation API for ORB.",
)

# In development we keep CORS open for easier local testing.
allow_origins = ["*"] if settings.environment.lower() == "development" else [f"https://{settings.platform_domain}"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next: Callable) -> JSONResponse:
    """Adds request timing metadata to every response."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Returns a safe, consistent JSON error payload for unhandled errors."""
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})


@app.get("/health")
def health_check() -> dict[str, Any]:
    """Checks API, database, and both AI provider connections."""
    services = {
        "database": "disconnected",
        "claude": "disconnected",
        "openai": "disconnected",
    }

    try:
        SupabaseClient().select("owners", {})
        services["database"] = "connected"
    except Exception:
        services["database"] = "disconnected"

    try:
        ping_claude()
        services["claude"] = "connected"
    except Exception:
        services["claude"] = "disconnected"

    try:
        ask_gpt_mini(prompt="Reply with exactly: hello", max_tokens=8)
        services["openai"] = "connected"
    except Exception:
        services["openai"] = "disconnected"

    return {
        "status": "healthy",
        "platform": settings.platform_name,
        "version": "0.1.0",
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


@app.get("/")
def root() -> dict[str, str]:
    """Simple root route to verify API booted."""
    return {"message": "ORB Platform API is running."}


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Ensures HTTP errors return clean JSON for beginners and frontend calls."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(agents.router)
app.include_router(wholesale.router)
app.include_router(assistant.router)
app.include_router(trading.router)
app.include_router(content.router)
app.include_router(identity.router)
app.include_router(webhooks.router)
app.include_router(auth.router)
