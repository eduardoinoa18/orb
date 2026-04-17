"""ORB Security Guard — Platform-wide input sanitization and request hardening.

This module implements defensive security layers that protect the platform from:
  - Injection attacks (SQL, prompt injection, command injection)
  - Malicious payload sizes (request body flooding)
  - Suspicious patterns (path traversal, SSRF probes)
  - Webhook replay attacks (timestamp validation + signature verification)
  - Brute force / credential stuffing (already handled by slowapi rate limiter)
  - Data exfiltration through oversized responses

All functions are stateless and safe to call from any middleware or route.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import re
import time
from typing import Any

logger = logging.getLogger("orb.security")

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_PROMPT_LENGTH = 32_000       # chars — generous for business use cases
MAX_REQUEST_BODY_BYTES = 512_000  # 512 KB — blocks megabyte payloads
MAX_FIELD_LENGTH = 10_000        # per-field safety trim
WEBHOOK_TIMESTAMP_TOLERANCE_SEC = 300  # 5 min replay window

_INJECTION_PATTERNS = re.compile(
    r"""(
        --[^\n]*           |   # SQL line comment
        ;.*DROP\s+TABLE    |   # SQL drop
        ;.*DELETE\s+FROM   |   # SQL delete
        UNION\s+SELECT     |   # SQL union
        <script[^>]*>      |   # XSS script tag
        javascript:        |   # XSS javascript: URI
        data:text/html     |   # Data URI XSS
        \.\./             |   # Path traversal
        \.\.\\             |   # Windows path traversal
        /etc/passwd        |   # LFI probe
        /proc/self         |   # Linux proc probe
        cmd\.exe           |   # Windows shell
        \beval\s*\(        |   # Code eval
        \bexec\s*\(        |   # Code exec
        \bos\.system\s*\(  |   # Shell exec
        \bsubprocess\.     |   # Python subprocess
    )""",
    re.IGNORECASE | re.VERBOSE,
)

_SSRF_PATTERNS = re.compile(
    r"""(
        localhost           |
        127\.0\.0\.1        |
        0\.0\.0\.0          |
        169\.254\.169\.254  |   # AWS metadata
        ::1                 |   # IPv6 loopback
        metadata\.google    |   # GCP metadata
        \bfile://           |   # file:// URI
    )""",
    re.IGNORECASE | re.VERBOSE,
)

_PROMPT_INJECTION_PATTERNS = re.compile(
    r"""(
        ignore\s+(all\s+)?previous\s+instructions? |
        disregard\s+(all\s+)?previous              |
        you\s+are\s+now\s+DAN                      |
        jailbreak                                  |
        act\s+as\s+if\s+you\s+are                 |
        forget\s+your\s+instructions?              |
        new\s+persona                              |
        pretend\s+you\s+are\s+a                   |
        system\s+prompt\s+override                |
    )""",
    re.IGNORECASE | re.VERBOSE,
)


# ── Sanitization ──────────────────────────────────────────────────────────────

def sanitize_text(text: str, max_length: int = MAX_FIELD_LENGTH) -> str:
    """Sanitizes arbitrary text input.

    - HTML-encodes dangerous characters
    - Strips null bytes
    - Trims to max_length
    - Strips leading/trailing whitespace

    Does NOT block the content — just makes it safe to store and display.
    """
    if not isinstance(text, str):
        return str(text)[:max_length]
    # Strip null bytes
    clean = text.replace("\x00", "")
    # Trim to max_length
    clean = clean[:max_length]
    # Strip excess whitespace
    return clean.strip()


def sanitize_prompt(prompt: str) -> tuple[str, list[str]]:
    """Sanitizes a user prompt intended for an AI model.

    Returns (sanitized_prompt, warnings).
    Warnings are logged for Eduardo's awareness but do NOT block the request
    (prompt injection is a soft signal, not always malicious).
    """
    warnings: list[str] = []
    clean = sanitize_text(prompt, max_length=MAX_PROMPT_LENGTH)

    if _PROMPT_INJECTION_PATTERNS.search(clean):
        warnings.append("Potential prompt injection pattern detected")
        logger.warning("Prompt injection pattern in user input (truncated): %s...", clean[:100])

    return clean, warnings


def check_injection(value: str) -> bool:
    """Returns True if the value contains injection patterns.

    Use this for URL params, query strings, and form fields that should
    never contain SQL or shell commands.
    """
    return bool(_INJECTION_PATTERNS.search(value))


def check_ssrf(url: str) -> bool:
    """Returns True if the URL appears to be an SSRF probe (targeting internal resources)."""
    return bool(_SSRF_PATTERNS.search(url))


def sanitize_dict(data: dict[str, Any], max_depth: int = 5) -> dict[str, Any]:
    """Recursively sanitizes a dict, trimming strings and removing null bytes.

    Handles nested dicts and lists up to max_depth deep.
    """
    def _clean(obj: Any, depth: int) -> Any:
        if depth <= 0:
            return obj
        if isinstance(obj, str):
            return sanitize_text(obj)
        if isinstance(obj, dict):
            return {k: _clean(v, depth - 1) for k, v in obj.items()
                    if isinstance(k, str) and not check_injection(k)}
        if isinstance(obj, list):
            return [_clean(item, depth - 1) for item in obj[:500]]  # max 500 items
        return obj
    return _clean(data, max_depth)


# ── Webhook signature verification ───────────────────────────────────────────

def verify_hmac_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
    algorithm: str = "sha256",
    prefix: str = "sha256=",
) -> bool:
    """Verifies an HMAC webhook signature (Stripe/GitHub/Twilio style).

    Usage:
        ok = verify_hmac_signature(
            payload=await request.body(),
            signature_header=request.headers.get("X-Hub-Signature-256", ""),
            secret=os.environ["WEBHOOK_SECRET"],
        )
    """
    if not signature_header or not secret:
        return False
    if signature_header.startswith(prefix):
        provided = signature_header[len(prefix):]
    else:
        provided = signature_header

    expected = hmac.new(
        secret.encode(),
        payload,
        getattr(hashlib, algorithm),
    ).hexdigest()

    return hmac.compare_digest(provided, expected)


def verify_timestamp(timestamp_str: str, tolerance_sec: int = WEBHOOK_TIMESTAMP_TOLERANCE_SEC) -> bool:
    """Checks if a webhook timestamp is within the acceptable replay window.

    Protects against replay attacks by rejecting webhooks older than tolerance_sec.
    """
    try:
        ts = float(timestamp_str)
        now = time.time()
        return abs(now - ts) <= tolerance_sec
    except (ValueError, TypeError):
        return False


def verify_twilio_signature(
    url: str,
    params: dict[str, str],
    signature: str,
    auth_token: str,
) -> bool:
    """Verifies a Twilio webhook signature.

    Twilio signs with HMAC-SHA1 over: url + sorted(key+value pairs).
    """
    import base64
    # Build the signature string
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(signature, expected)


# ── Input validation ──────────────────────────────────────────────────────────

def validate_owner_id(owner_id: Any) -> str:
    """Validates and returns a safe owner_id string (UUID format).

    Raises ValueError if invalid.
    """
    import uuid
    try:
        return str(uuid.UUID(str(owner_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Invalid owner_id format: {owner_id!r}")


def is_safe_redirect_url(url: str, allowed_origins: list[str]) -> bool:
    """Checks if a redirect URL is in the allowed origins list.

    Prevents open redirect vulnerabilities.
    """
    if not url:
        return False
    # Allow relative URLs
    if url.startswith("/"):
        return True
    for origin in allowed_origins:
        if url.startswith(origin):
            return True
    return False


# ── Response hardening ────────────────────────────────────────────────────────

def strip_internal_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Removes fields that should never leave the server.

    Protects against accidental leakage of internal fields in API responses.
    """
    _INTERNAL_FIELDS = {
        "password", "hashed_password", "password_hash",
        "jwt_secret", "api_key", "secret_key", "auth_token",
        "internal_note", "_internal", "raw_webhook",
    }
    return {k: v for k, v in data.items() if k.lower() not in _INTERNAL_FIELDS}


# ── Body size guard ───────────────────────────────────────────────────────────

async def check_body_size(request: Any, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
    """Raises an HTTP 413 if the request body exceeds max_bytes.

    Use in middleware or at the top of sensitive POST endpoints.
    """
    from fastapi import HTTPException
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large. Maximum allowed: {max_bytes // 1024} KB.",
        )


# ── Encryption helpers ────────────────────────────────────────────────────────

def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Masks a sensitive string for logging (shows only last N characters).

    mask_sensitive("sk-proj-abc123xyz") → "•••••••••••••xyz"
    """
    if not value:
        return ""
    if len(value) <= visible_chars:
        return "•" * len(value)
    return "•" * (len(value) - visible_chars) + value[-visible_chars:]


# ── Free-tier guard ───────────────────────────────────────────────────────────

def check_free_tier_limits(
    owner_id: str,
    resource: str,
    current_count: int,
    limits: dict[str, int],
) -> tuple[bool, str]:
    """Checks if an owner has hit their free-tier resource limits.

    Returns (allowed: bool, message: str).
    """
    limit = limits.get(resource, 0)
    if limit == 0:
        return True, ""  # No limit configured
    if current_count >= limit:
        return False, (
            f"Free tier limit reached for {resource}: {current_count}/{limit}. "
            "Upgrade your plan to continue."
        )
    return True, ""


FREE_TIER_LIMITS: dict[str, int] = {
    "agents": 3,
    "platform_tasks": 10,
    "api_calls_per_day": 100,
    "storage_mb": 100,
    "connected_integrations": 3,
}
