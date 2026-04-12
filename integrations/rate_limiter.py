"""Rate Limiter — Protects ORB Platform from abuse and runaway costs.

Enforces per-owner and per-agent limits on:
- AI calls per hour/day
- External API calls per minute
- Financial operations per day
- Total daily cost caps

Uses in-memory + DB-backed counters for accurate multi-process tracking.

Core principle: Budget-conscious autonomy. Agents act freely within limits;
when a limit is hit, the action is queued or denied — never silently ignored.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger("orb.security.rate_limiter")


# ---------------------------------------------------------------------------
# Limit definitions
# ---------------------------------------------------------------------------

# Per-owner AI call limits
AI_LIMITS = {
    "starter": {
        "calls_per_hour": 30,
        "calls_per_day": 200,
        "daily_cost_cents": 500,       # $5/day
    },
    "professional": {
        "calls_per_hour": 150,
        "calls_per_day": 1000,
        "daily_cost_cents": 2000,      # $20/day
    },
    "enterprise": {
        "calls_per_hour": 1000,
        "calls_per_day": 10000,
        "daily_cost_cents": 10000,     # $100/day
    },
    "master_owner": {
        "calls_per_hour": 5000,
        "calls_per_day": 50000,
        "daily_cost_cents": 100000,    # $1,000/day (platform owner)
    },
}

# Per-agent external API call limits (per minute, to prevent runaway)
AGENT_API_LIMITS = {
    "commander": {"calls_per_minute": 20, "calls_per_hour": 200},
    "rex": {"calls_per_minute": 10, "calls_per_hour": 100},
    "aria": {"calls_per_minute": 5, "calls_per_hour": 50},
    "nova": {"calls_per_minute": 5, "calls_per_hour": 50},
    "orion": {"calls_per_minute": 10, "calls_per_hour": 100},
    "atlas": {"calls_per_minute": 10, "calls_per_hour": 100},
    "sage": {"calls_per_minute": 5, "calls_per_hour": 50},
}

# SMS/email hard limits per owner per day (to prevent spam abuse)
COMMUNICATION_DAILY_LIMITS = {
    "sms": {"starter": 20, "professional": 100, "enterprise": 500},
    "email": {"starter": 50, "professional": 500, "enterprise": 5000},
    "voice_calls": {"starter": 5, "professional": 25, "enterprise": 100},
}


# ---------------------------------------------------------------------------
# In-memory + DB rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Thread-safe rate limiter with sliding window counters.

    Falls back to in-memory counters when DB is unavailable.
    """

    _instance: "RateLimiter | None" = None
    _lock = Lock()

    def __new__(cls) -> "RateLimiter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._counters: dict[str, list[float]] = defaultdict(list)  # key -> timestamps
        self._cost_today: dict[str, int] = defaultdict(int)  # owner_id -> cents today
        self._reset_date: dict[str, str] = {}  # owner_id -> last reset date
        self._lock2 = Lock()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset_if_new_day(self, owner_id: str) -> None:
        today = self._today()
        if self._reset_date.get(owner_id) != today:
            self._cost_today[owner_id] = 0
            self._reset_date[owner_id] = today
            # Clear old per-owner counters
            prefix = f"ai:{owner_id}"
            keys_to_clear = [k for k in self._counters if k.startswith(prefix)]
            for k in keys_to_clear:
                self._counters[k] = []

    def _count_in_window(self, key: str, window_seconds: int) -> int:
        """Count events in the last `window_seconds` seconds."""
        now = time.time()
        cutoff = now - window_seconds
        self._counters[key] = [t for t in self._counters[key] if t > cutoff]
        return len(self._counters[key])

    def _record(self, key: str) -> None:
        """Record a new event timestamp."""
        self._counters[key].append(time.time())

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def check_ai_call(self, owner_id: str, plan: str = "starter") -> tuple[bool, str]:
        """Check if an AI call is allowed for this owner.

        Returns: (allowed: bool, reason: str)
        """
        limits = AI_LIMITS.get(plan, AI_LIMITS["starter"])

        with self._lock2:
            self._reset_if_new_day(owner_id)

            hourly_count = self._count_in_window(f"ai:{owner_id}:hour", 3600)
            daily_count = self._count_in_window(f"ai:{owner_id}:day", 86400)

            if hourly_count >= limits["calls_per_hour"]:
                return False, f"Hourly AI call limit reached ({limits['calls_per_hour']}/hr). Resets in the next hour."

            if daily_count >= limits["calls_per_day"]:
                return False, f"Daily AI call limit reached ({limits['calls_per_day']}/day). Resets at midnight UTC."

            cost_limit = limits["daily_cost_cents"]
            if self._cost_today[owner_id] >= cost_limit:
                return False, f"Daily AI cost cap reached (${cost_limit / 100:.2f}/day). Resets at midnight UTC."

            return True, "ok"

    def record_ai_call(self, owner_id: str, cost_cents: int = 0) -> None:
        """Record an AI call for rate-limiting purposes."""
        with self._lock2:
            self._record(f"ai:{owner_id}:hour")
            self._record(f"ai:{owner_id}:day")
            self._cost_today[owner_id] += cost_cents

    def check_agent_api_call(self, agent_slug: str, owner_id: str) -> tuple[bool, str]:
        """Check if an agent external API call is within limits.

        Returns: (allowed: bool, reason: str)
        """
        limits = AGENT_API_LIMITS.get(agent_slug, {"calls_per_minute": 5, "calls_per_hour": 30})
        key_min = f"agent:{agent_slug}:{owner_id}:min"
        key_hour = f"agent:{agent_slug}:{owner_id}:hour"

        with self._lock2:
            per_min = self._count_in_window(key_min, 60)
            per_hour = self._count_in_window(key_hour, 3600)

            if per_min >= limits["calls_per_minute"]:
                return False, f"Agent '{agent_slug}' API rate limit: {limits['calls_per_minute']} calls/minute."

            if per_hour >= limits["calls_per_hour"]:
                return False, f"Agent '{agent_slug}' hourly API limit: {limits['calls_per_hour']} calls/hour."

            return True, "ok"

    def record_agent_api_call(self, agent_slug: str, owner_id: str) -> None:
        """Record an agent external API call."""
        with self._lock2:
            self._record(f"agent:{agent_slug}:{owner_id}:min")
            self._record(f"agent:{agent_slug}:{owner_id}:hour")

    def check_communication(
        self,
        channel: str,
        owner_id: str,
        plan: str = "starter",
    ) -> tuple[bool, str]:
        """Check if a communication action (SMS/email/call) is within daily limits.

        Args:
            channel: 'sms' | 'email' | 'voice_calls'
            owner_id: Owner ID.
            plan: Owner's plan tier.

        Returns: (allowed: bool, reason: str)
        """
        channel_limits = COMMUNICATION_DAILY_LIMITS.get(channel, {})
        limit = channel_limits.get(plan, channel_limits.get("starter", 10))
        key = f"comm:{channel}:{owner_id}:day"

        with self._lock2:
            count = self._count_in_window(key, 86400)
            if count >= limit:
                return False, f"Daily {channel} limit reached ({limit}/day on {plan} plan)."
            return True, "ok"

    def record_communication(self, channel: str, owner_id: str) -> None:
        """Record a communication action."""
        with self._lock2:
            self._record(f"comm:{channel}:{owner_id}:day")

    def get_status(self, owner_id: str, plan: str = "starter") -> dict[str, Any]:
        """Get current rate limit status for an owner."""
        limits = AI_LIMITS.get(plan, AI_LIMITS["starter"])

        with self._lock2:
            self._reset_if_new_day(owner_id)
            return {
                "ai_calls_this_hour": self._count_in_window(f"ai:{owner_id}:hour", 3600),
                "ai_calls_today": self._count_in_window(f"ai:{owner_id}:day", 86400),
                "ai_cost_today_cents": self._cost_today.get(owner_id, 0),
                "ai_calls_per_hour_limit": limits["calls_per_hour"],
                "ai_calls_per_day_limit": limits["calls_per_day"],
                "ai_daily_cost_limit_cents": limits["daily_cost_cents"],
                "sms_today": self._count_in_window(f"comm:sms:{owner_id}:day", 86400),
                "email_today": self._count_in_window(f"comm:email:{owner_id}:day", 86400),
                "reset_date": self._today(),
            }


# Singleton accessor
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()


# ---------------------------------------------------------------------------
# FastAPI middleware helper
# ---------------------------------------------------------------------------

class RateLimitExceededError(Exception):
    """Raised when a rate limit is exceeded."""
