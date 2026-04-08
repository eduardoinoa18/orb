"""ORB Rate Limiting — Module 4, Step S4.

Uses slowapi (Starlette-compatible wrapper around limits) to enforce
per-endpoint and per-IP request rate limits.

Rate tiers:
    auth endpoints      — 10 requests / minute  (brute-force deterrent)
    webhook endpoints   — 60 requests / minute  (high-frequency ok)
    agent endpoints     — 30 requests / minute  (medium volume)
    dashboard endpoints — 120 requests / minute (browser navigation)
    default             — 60 requests / minute

Usage in a route:
    from app.api.middleware.rate_limit import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    @router.post("/login")
    @limiter.limit("10/minute")
    async def login(request: Request, ...):
        ...

To wire into FastAPI app (done in main.py):
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from app.api.middleware.rate_limit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# ---------------------------------------------------------------------------
# Global limiter — key by client IP
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


# ---------------------------------------------------------------------------
# Named rate-limit strings for consistent reuse across route files
# ---------------------------------------------------------------------------

RATE_AUTH = "10/minute"        # Login, token refresh
RATE_WEBHOOK = "60/minute"     # TradingView, Twilio, N8N
RATE_AGENT = "30/minute"       # Atlas, Rex, Aria, Nova, Orion, Sage
RATE_DASHBOARD = "120/minute"  # Dashboard reads
RATE_SETUP = "20/minute"       # Setup wizard (save-key, test-key)
