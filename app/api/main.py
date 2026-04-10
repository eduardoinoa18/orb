"""Main FastAPI application for ORB Level 1.

This file creates the web server, adds middleware, and exposes the first test
endpoint: GET /health.
"""

import asyncio
import logging
import time
import uuid as uuid_module
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from swagger_ui_bundle import swagger_ui_path

from config.settings import get_settings
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.middleware.rate_limit import limiter
from app.api.routes import (
    access,
    agents,
    agent_settings,
    aria,
    auth_google,
    billing,
    commander,
    commander_settings,
    computer_use,
    content,
    dashboard,
    onboarding,
    optimization,
    orion,
    rex,
    sage,
    superadmin,
    trading,
    websocket,
    webhooks,
    wholesale,
)
from app.api.routes import atlas
from app.api.routes import integrations
from app.api.routes import setup
from app.database.connection import DatabaseConnectionError, SupabaseService
from app.ui_shell import render_dashboard, render_home, render_login
from app.runtime.preflight import build_preflight_report
from agents.aria.briefing_scheduler import AriaBriefingScheduler
from agents.sage.monitor_scheduler import SageMonitorScheduler

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orb.api")


_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data:; "
    "font-src 'self' data: https://fonts.gstatic.com;"
)

_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data:; "
    "font-src 'self' data: https://fonts.gstatic.com;"
)


def _csp_for_path(path: str) -> str:
    docs_paths = ("/docs",)
    if path in docs_paths:
        return _DOCS_CSP
    return _DEFAULT_CSP


def _looks_placeholder(value: str) -> bool:
    lowered = (value or "").strip().lower()
    if not lowered:
        return True
    marker_words = (
        "placeholder",
        "replace",
        "changeme",
        "example",
        "test",
        "your_",
        "your-",
    )
    return any(word in lowered for word in marker_words)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup/shutdown lifecycle hooks."""
    if settings.aria_briefing_enabled:
        aria_scheduler = AriaBriefingScheduler()
        aria_scheduler.start()
        app.state.aria_briefing_scheduler = aria_scheduler
    else:
        app.state.aria_briefing_scheduler = None
        logger.info("Aria briefing scheduler disabled for lean launch")

    if settings.sage_monitor_enabled:
        sage_scheduler = SageMonitorScheduler()
        sage_scheduler.start()
        app.state.sage_monitor_scheduler = sage_scheduler
    else:
        app.state.sage_monitor_scheduler = None
        logger.info("Sage monitor scheduler disabled for lean launch")
    try:
        yield
    finally:
        aria_active = getattr(app.state, "aria_briefing_scheduler", None)
        if aria_active:
            aria_active.stop()

        sage_active = getattr(app.state, "sage_monitor_scheduler", None)
        if sage_active:
            sage_active.stop()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="ORB AI Agent Identity Platform API",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.mount("/docs-assets", StaticFiles(directory=swagger_ui_path), name="docs-assets")

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Callable):
    """Add OWASP-recommended security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = _csp_for_path(request.url.path)
    # Only send HSTS on HTTPS — skip on localhost
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Callable):
    """Logs each request path, method, response time, and request ID."""
    request_id = request.headers.get("X-Request-ID") or str(uuid_module.uuid4())
    request.state.request_id = request_id
    
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    response.headers["X-Process-Time-Ms"] = str(round(duration_ms, 2))
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next: Callable):
    """Validates bearer tokens for protected routes while keeping health public."""
    public_paths = {
        # Core
        "/",
        "/api",
        "/health",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
        # Auth flows — must be public for redirect to work
        "/login",
        "/auth/google/start",
        "/auth/google/callback",
        "/aria/google/authorize",
        "/aria/google/connect",
        # Onboarding + Auth — unauthenticated flows
        "/onboarding/login",
        "/onboarding/register",
        "/onboarding/about",
        "/onboarding/commander",
        "/onboarding/plan",
        "/onboarding/first-agent",
        "/onboarding/connect-tool",
        # Inbound webhooks — signed by external provider, not by JWT
        "/webhooks/stripe",
        "/webhooks/tradingview",
        "/webhooks/twilio/sms",
        "/webhooks/whatsapp/incoming",
        "/webhooks/email/incoming",
        "/webhooks/n8n/error",
        "/webhooks/n8n/complete",
        "/webhooks/status",
        # Public status endpoints (read-only, no secrets)
        "/setup/preflight",
        "/setup/schema-readiness",
        "/setup/status",
    }

    public_prefixes = (
        "/docs/",
        "/docs-assets/",
        "/onboarding/status/",
    )

    if request.url.path in public_paths or any(request.url.path.startswith(prefix) for prefix in public_prefixes):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing bearer token."},
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        request.state.token_payload = payload
    except JWTError:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or expired token."},
        )

    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Returns a consistent JSON response for FastAPI HTTP exceptions."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Catches unexpected errors and returns a safe JSON response."""
    logger.exception("Unhandled application error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    """Human-friendly homepage for local browser testing."""
    return render_home()


@app.get("/api")
def root_api() -> dict[str, str]:
    """JSON root kept for API-first clients."""
    return {"message": "Welcome to ORB"}


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/docs-assets/swagger-ui-bundle.js",
        swagger_css_url="/docs-assets/swagger-ui.css",
        swagger_favicon_url="/docs-assets/favicon-32x32.png",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_placeholder() -> str:
    """Command-center dashboard shell until React frontend is connected."""
    return render_dashboard(_build_dashboard_metrics())


def _build_dashboard_metrics() -> dict[str, object]:
    """Aggregates lightweight dashboard metrics from Supabase with safe fallbacks."""
    try:
        db = SupabaseService()
        agents_rows = db.fetch_all("agents")
        trades_rows = db.fetch_all("trades")
        activity_rows = db.fetch_all("activity_log")
    except DatabaseConnectionError:
        return {
            "active_agents": 0,
            "pending_approvals": 0,
            "daily_cost_dollars": 0.0,
            "recent_activity": [],
            "agents": [],
            "quick_actions": [
                "POST /webhooks/tradingview",
                "POST /webhooks/twilio/sms",
                "POST /test/database",
            ],
            "db_status": "offline",
        }

    active_agents = sum(1 for row in agents_rows if row.get("status") == "active")
    pending_trades = sum(1 for row in trades_rows if row.get("status") == "pending_approval")
    pending_activity = sum(1 for row in activity_rows if row.get("needs_approval") is True)

    now_date = datetime.now(timezone.utc).date()
    daily_cost_cents = 0
    for row in activity_rows:
        created_at = row.get("created_at")
        if not created_at:
            continue
        try:
            row_date = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if row_date == now_date:
            daily_cost_cents += int(row.get("cost_cents") or 0)

    recent_rows = sorted(
        activity_rows,
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )[:5]
    recent_activity = [
        f"{row.get('action_type', 'event')}: {row.get('description', 'No description')}"
        for row in recent_rows
    ]

    agent_last_action: dict[str, str] = {}
    for row in recent_rows:
        agent_id = row.get("agent_id")
        if agent_id and agent_id not in agent_last_action:
            agent_last_action[str(agent_id)] = str(row.get("description") or "No recent action")

    agent_cards = []
    for row in agents_rows[:8]:
        agent_id = str(row.get("id") or "")
        agent_cards.append(
            {
                "id": agent_id,
                "name": str(row.get("name") or "Unnamed agent"),
                "role": str(row.get("role") or "unknown"),
                "status": str(row.get("status") or "unknown"),
                "last_action": agent_last_action.get(agent_id, "No recent action"),
            }
        )

    return {
        "active_agents": active_agents,
        "pending_approvals": pending_trades + pending_activity,
        "daily_cost_dollars": round(daily_cost_cents / 100, 2),
        "recent_activity": recent_activity,
        "agents": agent_cards,
        "quick_actions": [
            "POST /webhooks/tradingview",
            "POST /webhooks/twilio/sms",
            "POST /test/database",
            "POST /test/claude",
        ],
        "db_status": "connected",
    }


@app.get("/dashboard/data")
def dashboard_data() -> dict[str, object]:
    """JSON data endpoint for dashboard UI shells and future React frontend."""
    return _build_dashboard_metrics()


@app.get("/login", response_class=HTMLResponse)
def login_placeholder() -> str:
    """Login shell page until Supabase Auth UI is built."""
    return render_login()


@app.get("/health")
async def health_check(deep: bool = False) -> dict[str, object]:
    """
    Health check endpoint with dependency verification.
    
    Checks:
    - Supabase connectivity (2 second timeout)
    - Anthropic API accessibility (2 second timeout)
    - OpenAI API accessibility (2 second timeout)
    
    Returns overall health status and per-dependency status.
    """
    TIMEOUT_SECONDS = 2
    
    async def check_supabase() -> dict[str, str]:
        """Check Supabase connectivity."""
        try:
            db = SupabaseService()
            await asyncio.wait_for(
                asyncio.to_thread(lambda: db.client.table("activity_log").select("id").limit(1).execute()),
                timeout=TIMEOUT_SECONDS
            )
            return {"status": "healthy", "error": None}
        except asyncio.TimeoutError:
            return {"status": "unhealthy", "error": "timeout"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:80]}
    
    async def check_anthropic() -> dict[str, str]:
        """Check Anthropic accessibility (config-only unless deep mode is requested)."""
        if not deep:
            key = settings.resolve("anthropic_api_key")
            if _looks_placeholder(key):
                return {"status": "unhealthy", "error": "missing_or_placeholder_key"}
            return {"status": "healthy", "error": None}

        try:
            from integrations.anthropic_client import ask_claude
            
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: ask_claude(
                        system="You are a health check service.",
                        prompt="Respond with 'healthy' and nothing else.",
                    )
                ),
                timeout=TIMEOUT_SECONDS
            )
            return {"status": "healthy", "error": None}
        except asyncio.TimeoutError:
            return {"status": "unhealthy", "error": "timeout"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:80]}
    
    async def check_openai() -> dict[str, str]:
        """Check OpenAI accessibility (config-only unless deep mode is requested)."""
        if not deep:
            key = settings.resolve("openai_api_key")
            if _looks_placeholder(key):
                return {"status": "unhealthy", "error": "missing_or_placeholder_key"}
            return {"status": "healthy", "error": None}

        try:
            from integrations.openai_client import ask_gpt_mini
            
            await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: ask_gpt_mini(
                        system="You are a health check service.",
                        prompt="Respond with 'healthy' and nothing else.",
                    )
                ),
                timeout=TIMEOUT_SECONDS
            )
            return {"status": "healthy", "error": None}
        except asyncio.TimeoutError:
            return {"status": "unhealthy", "error": "timeout"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:80]}
    
    # Run all checks in parallel
    supabase_health, anthropic_health, openai_health = await asyncio.gather(
        check_supabase(),
        check_anthropic(),
        check_openai(),
    )
    
    # Overall health is healthy only if all dependencies are healthy
    all_healthy = (
        supabase_health["status"] == "healthy"
        and anthropic_health["status"] == "healthy"
        and openai_health["status"] == "healthy"
    )
    preflight = build_preflight_report()
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "platform": settings.app_name,
        "version": settings.app_version,
        "dependencies": {
            "supabase": supabase_health,
            "anthropic": anthropic_health,
            "openai": openai_health,
        },
        "mode": "deep" if deep else "standard",
        "preflight": {
            "ready": preflight.get("ready", False),
            "score": preflight.get("score", 0),
            "summary": preflight.get("summary", {}),
        },
    }


app.include_router(agents.router)
app.include_router(access.router)
app.include_router(agent_settings.router)
app.include_router(aria.router)
app.include_router(auth_google.router)
app.include_router(atlas.router)
app.include_router(billing.router)
app.include_router(commander.router)
app.include_router(commander_settings.router)
app.include_router(integrations.router)
app.include_router(onboarding.router)
app.include_router(content.router)
app.include_router(setup.router)
app.include_router(dashboard.router)
app.include_router(optimization.router)
app.include_router(orion.router)
app.include_router(rex.router)
app.include_router(sage.router)
app.include_router(computer_use.router)
app.include_router(trading.router)
app.include_router(wholesale.router)
app.include_router(superadmin.router)
app.include_router(websocket.router)
app.include_router(webhooks.router)
