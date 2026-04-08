"""ORB Input Validator — Module 4, Step S3.

Provides safe sanitisation and validation routines for all user-supplied
data entering the platform.  Uses:
  - bleach   → HTML / XSS sanitisation
  - email_validator → RFC 5321-compliant email validation
  - phonenumbers → E.164 phone number normalisation

All functions are pure and raise ValueError with a descriptive message
on bad input — never swallow or ignore invalid data silently.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


# ---------------------------------------------------------------------------
# HTML / XSS Sanitization
# ---------------------------------------------------------------------------

# Whitelist tags allowed in rich-text fields (e.g. email bodies)
_ALLOWED_TAGS: list[str] = ["b", "i", "u", "em", "strong", "p", "br", "ul", "ol", "li"]
_ALLOWED_ATTRS: dict[str, list[str]] = {}


def sanitize_text(value: str, allow_html: bool = False) -> str:
    """Remove dangerous HTML / script content from *value*.

    If *allow_html* is False (default), strip ALL tags — safe for
    plain-text fields like names, addresses, notes.

    If *allow_html* is True, allow the whitelist tags only — for email body text.
    """
    import bleach
    if not isinstance(value, str):
        raise ValueError(f"Expected str, got {type(value).__name__}")
    if allow_html:
        return bleach.clean(value, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)
    return bleach.clean(value, tags=[], attributes={}, strip=True)


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

def validate_email(email: str) -> str:
    """Validate and normalise *email*.

    Returns the normalised email string (lower-cased, trimmed).
    Raises ValueError if the format is invalid.
    """
    from email_validator import validate_email as _validate, EmailNotValidError
    try:
        info = _validate(email, check_deliverability=False)
        return info.normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError(f"Invalid email address: {exc}") from exc


# ---------------------------------------------------------------------------
# Phone number validation
# ---------------------------------------------------------------------------

def validate_phone(phone: str, default_region: str = "US") -> str:
    """Parse and normalise *phone* to E.164 format (e.g. +12025551234).

    Raises ValueError if the number is invalid.
    """
    import phonenumbers
    from phonenumbers import NumberParseException, PhoneNumberFormat
    try:
        parsed = phonenumbers.parse(phone, default_region)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError(f"Phone number is not valid: {phone!r}")
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException as exc:
        raise ValueError(f"Cannot parse phone number {phone!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_URL_PATTERN = re.compile(
    r'^https?://'                       # http:// or https://
    r'(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}'  # domain
    r'(?::\d+)?'                        # optional port
    r'(?:/[^\s]*)?$',                   # optional path
    re.IGNORECASE,
)


def validate_url(url: str, https_only: bool = True) -> str:
    """Validate that *url* is a well-formed URL.

    If *https_only* is True (default), reject plain http:// URLs.
    Returns the stripped URL.
    Raises ValueError on invalid input.
    """
    url = url.strip()
    if not _URL_PATTERN.match(url):
        raise ValueError(f"Invalid URL: {url!r}")
    if https_only and url.lower().startswith("http://"):
        raise ValueError(f"Only HTTPS URLs are accepted: {url!r}")
    return url


# ---------------------------------------------------------------------------
# API key format check
# ---------------------------------------------------------------------------

def validate_api_key_format(key: str, prefix: str = "orb_") -> str:
    """Verify that *key* has a recognised format.

    Doesn't verify the key against the database — call verify_api_key() for that.
    Raises ValueError if the format is wrong.
    """
    key = key.strip()
    if not key.startswith(prefix):
        raise ValueError(f"API key must start with '{prefix}'")
    if len(key) < len(prefix) + 8:
        raise ValueError("API key is too short to be valid")
    return key


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------

class InputValidator:
    """Convenience wrapper that exposes all validators as instance methods."""

    sanitize_text = staticmethod(sanitize_text)
    validate_email = staticmethod(validate_email)
    validate_phone = staticmethod(validate_phone)
    validate_url = staticmethod(validate_url)
    validate_api_key_format = staticmethod(validate_api_key_format)


@lru_cache(maxsize=1)
def get_input_validator() -> InputValidator:
    """Return a cached InputValidator singleton."""
    return InputValidator()
