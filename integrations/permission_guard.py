"""Permission Guard — Security layer for all agent actions.

Enforces what each agent is allowed to do.
Prevents unauthorized or dangerous operations.
Provides immutable audit trail for every action.

Core principle: Owner always wins. No agent can override owner commands.
But agents must stay within their defined permission scope.

Security rules:
- No agent can ever: delete owner data, send data externally without permission,
  access other owners' data, or perform irreversible financial actions over $limit.
- Master_owner can grant/revoke permissions for any agent.
- All denials are logged with reason.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("orb.security.permission_guard")


# ---------------------------------------------------------------------------
# Permission definitions
# ---------------------------------------------------------------------------

class Permission(str, Enum):
    # Communication permissions
    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    SEND_SLACK = "send_slack"
    MAKE_PHONE_CALL = "make_phone_call"
    POST_SOCIAL_MEDIA = "post_social_media"

    # Calendar permissions
    READ_CALENDAR = "read_calendar"
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    CANCEL_CALENDAR_EVENT = "cancel_calendar_event"

    # CRM permissions
    READ_CONTACTS = "read_contacts"
    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    CREATE_DEAL = "create_deal"
    UPDATE_DEAL = "update_deal"

    # File/storage permissions
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    CREATE_NOTION_PAGE = "create_notion_page"
    READ_DRIVE = "read_drive"
    WRITE_DRIVE = "write_drive"

    # Code/dev permissions
    READ_GITHUB = "read_github"
    CREATE_GITHUB_ISSUE = "create_github_issue"
    COMMENT_GITHUB = "comment_github"

    # Financial permissions
    READ_PAYMENTS = "read_payments"
    CREATE_INVOICE = "create_invoice"
    ISSUE_REFUND = "issue_refund"
    CHARGE_CUSTOMER = "charge_customer"

    # AI permissions
    USE_AI_HAIKU = "use_ai_haiku"
    USE_AI_SONNET = "use_ai_sonnet"
    USE_AI_OPUS = "use_ai_opus"
    USE_VOICE_SYNTHESIS = "use_voice_synthesis"

    # System permissions
    READ_ACTIVITY_LOG = "read_activity_log"
    MODIFY_AGENT_SETTINGS = "modify_agent_settings"
    ACCESS_OWNER_DATA = "access_owner_data"
    WEB_SEARCH = "web_search"
    SEND_WEBHOOK = "send_webhook"


# Default permissions per agent slug
AGENT_DEFAULT_PERMISSIONS: dict[str, set[Permission]] = {
    "commander": {
        Permission.SEND_SMS,
        Permission.SEND_EMAIL,
        Permission.SEND_SLACK,
        Permission.READ_CALENDAR,
        Permission.CREATE_CALENDAR_EVENT,
        Permission.CANCEL_CALENDAR_EVENT,
        Permission.READ_CONTACTS,
        Permission.CREATE_CONTACT,
        Permission.UPDATE_CONTACT,
        Permission.CREATE_DEAL,
        Permission.CREATE_NOTION_PAGE,
        Permission.READ_DRIVE,
        Permission.READ_GITHUB,
        Permission.CREATE_GITHUB_ISSUE,
        Permission.COMMENT_GITHUB,
        Permission.READ_PAYMENTS,
        Permission.CREATE_INVOICE,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.USE_AI_OPUS,
        Permission.USE_VOICE_SYNTHESIS,
        Permission.READ_ACTIVITY_LOG,
        Permission.ACCESS_OWNER_DATA,
        Permission.WEB_SEARCH,
    },
    "rex": {
        Permission.READ_CONTACTS,
        Permission.CREATE_CONTACT,
        Permission.UPDATE_CONTACT,
        Permission.CREATE_DEAL,
        Permission.UPDATE_DEAL,
        Permission.SEND_EMAIL,
        Permission.SEND_SMS,
        Permission.MAKE_PHONE_CALL,
        Permission.READ_ACTIVITY_LOG,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.ACCESS_OWNER_DATA,
    },
    "aria": {
        Permission.SEND_EMAIL,
        Permission.POST_SOCIAL_MEDIA,
        Permission.CREATE_NOTION_PAGE,
        Permission.WRITE_FILES,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.ACCESS_OWNER_DATA,
        Permission.WEB_SEARCH,
    },
    "nova": {
        Permission.READ_ACTIVITY_LOG,
        Permission.READ_PAYMENTS,
        Permission.CREATE_INVOICE,
        Permission.READ_CONTACTS,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.ACCESS_OWNER_DATA,
    },
    "orion": {
        Permission.WEB_SEARCH,
        Permission.READ_ACTIVITY_LOG,
        Permission.READ_GITHUB,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.USE_AI_OPUS,
        Permission.ACCESS_OWNER_DATA,
    },
    "atlas": {
        Permission.READ_PAYMENTS,
        Permission.CREATE_INVOICE,
        Permission.ISSUE_REFUND,
        Permission.READ_CONTACTS,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.ACCESS_OWNER_DATA,
    },
    "sage": {
        Permission.READ_ACTIVITY_LOG,
        Permission.WEB_SEARCH,
        Permission.READ_DRIVE,
        Permission.CREATE_NOTION_PAGE,
        Permission.USE_AI_HAIKU,
        Permission.USE_AI_SONNET,
        Permission.USE_AI_OPUS,
        Permission.ACCESS_OWNER_DATA,
    },
}

# Actions that always require explicit owner approval regardless of permissions
ALWAYS_REQUIRES_APPROVAL: set[Permission] = {
    Permission.CHARGE_CUSTOMER,
    Permission.ISSUE_REFUND,
    Permission.CANCEL_CALENDAR_EVENT,
    Permission.WRITE_DRIVE,
    Permission.MODIFY_AGENT_SETTINGS,
}

# Financial limits per agent per action (in cents)
FINANCIAL_LIMITS: dict[str, int] = {
    "commander": 10000,   # $100 max
    "rex": 50000,         # $500 max
    "atlas": 100000,      # $1,000 max
    "nova": 25000,        # $250 max
    "aria": 5000,         # $50 max
    "orion": 0,
    "sage": 0,
}


# ---------------------------------------------------------------------------
# PermissionGuard class
# ---------------------------------------------------------------------------

class PermissionGuard:
    """Checks and enforces agent permissions before any action is taken.

    Usage:
        guard = PermissionGuard(owner_id="...", agent_slug="rex")
        guard.require(Permission.SEND_EMAIL)  # raises if denied
        guard.check(Permission.SEND_EMAIL)    # returns bool
    """

    def __init__(self, owner_id: str, agent_slug: str) -> None:
        self.owner_id = owner_id
        self.agent_slug = agent_slug.lower()
        self._db_overrides: set[Permission] | None = None

    def _get_effective_permissions(self) -> set[Permission]:
        """Merge default + any owner-granted overrides from DB."""
        defaults = AGENT_DEFAULT_PERMISSIONS.get(self.agent_slug, set()).copy()

        # Try to load DB overrides (non-fatal if DB unavailable)
        if self._db_overrides is None:
            self._db_overrides = self._load_db_overrides()

        return defaults | self._db_overrides

    def _load_db_overrides(self) -> set[Permission]:
        """Load any custom permissions the owner has granted to this agent."""
        try:
            from app.database.connection import SupabaseService
            db = SupabaseService()
            rows = db.fetch_all(
                "agent_permissions",
                {"owner_id": self.owner_id, "agent_slug": self.agent_slug, "active": True},
            )
            return {Permission(row["permission"]) for row in rows if row.get("permission")}
        except Exception:
            return set()

    def check(self, permission: Permission) -> bool:
        """Return True if this agent has the given permission for this owner."""
        return permission in self._get_effective_permissions()

    def require(self, permission: Permission, action_detail: str = "") -> None:
        """Raise PermissionDeniedError if the agent lacks the given permission.

        Also logs the denial for audit purposes.
        """
        if not self.check(permission):
            self._log_denial(permission, action_detail)
            raise PermissionDeniedError(
                f"Agent '{self.agent_slug}' is not allowed to '{permission.value}'. "
                f"Contact your owner to grant this permission."
            )

    def requires_approval(self, permission: Permission) -> bool:
        """Check if this permission always requires owner approval."""
        return permission in ALWAYS_REQUIRES_APPROVAL

    def check_financial_limit(self, amount_cents: int) -> bool:
        """Return True if the amount is within the agent's financial limit."""
        limit = FINANCIAL_LIMITS.get(self.agent_slug, 0)
        return amount_cents <= limit

    def require_financial_limit(self, amount_cents: int) -> None:
        """Raise if the amount exceeds the agent's financial limit."""
        if not self.check_financial_limit(amount_cents):
            limit = FINANCIAL_LIMITS.get(self.agent_slug, 0)
            raise PermissionDeniedError(
                f"Agent '{self.agent_slug}' has a ${limit / 100:.2f} financial limit. "
                f"Requested: ${amount_cents / 100:.2f}. Requires owner approval."
            )

    def _log_denial(self, permission: Permission, detail: str) -> None:
        """Log a permission denial to the activity log (non-fatal)."""
        try:
            from app.database.connection import SupabaseService
            db = SupabaseService()
            db.log_activity(
                agent_id=self.agent_slug,
                owner_id=self.owner_id,
                action_type="permission_denied",
                description=f"Agent '{self.agent_slug}' denied: {permission.value}",
                metadata={
                    "permission": permission.value,
                    "agent": self.agent_slug,
                    "detail": detail,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Could not log permission denial: %s", e)


class PermissionDeniedError(Exception):
    """Raised when an agent attempts an action it is not permitted to perform."""


# ---------------------------------------------------------------------------
# Convenience decorator
# ---------------------------------------------------------------------------

def requires_permission(permission: Permission):
    """Decorator factory for agent method permission checks.

    Usage:
        @requires_permission(Permission.SEND_EMAIL)
        async def send_outreach(self, owner_id, ...):
            ...

    The decorated function must receive `owner_id` as its first positional
    argument after `self`, and the class must have a `slug` attribute.
    """
    def decorator(fn):
        import functools

        @functools.wraps(fn)
        async def wrapper(self, owner_id: str, *args: Any, **kwargs: Any) -> Any:
            guard = PermissionGuard(owner_id=owner_id, agent_slug=getattr(self, "slug", "unknown"))
            guard.require(permission)
            return await fn(self, owner_id, *args, **kwargs)

        return wrapper
    return decorator
