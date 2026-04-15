"""DocuSign eSignature client for ORB Platform.

Agents can use DocuSign to:
  - Send documents for electronic signature
  - Check envelope signing status
  - Get signed document URLs
  - Void/cancel envelopes
  - Create envelopes from templates
  - List recent envelopes

Use cases for real estate and professional services:
  - Buyer/seller agreements
  - Lease agreements
  - NDA and disclosure forms
  - Service contracts

Requires:
  DOCUSIGN_ACCOUNT_ID    — Account ID from DocuSign Admin
  DOCUSIGN_ACCESS_TOKEN  — OAuth access token (or API key for legacy apps)
  DOCUSIGN_BASE_URL      — API base URL (default: https://na4.docusign.net/restapi/v2.1)

Docs: https://developers.docusign.com/docs/esign-rest-api
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.docusign")

DEFAULT_BASE_URL = "https://na4.docusign.net/restapi/v2.1"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_docusign_available() -> bool:
    s = get_settings()
    return bool(
        s.resolve("docusign_account_id", default="")
        and s.resolve("docusign_access_token", default="")
    )


def _account_id() -> str:
    return get_settings().resolve("docusign_account_id", default="")


def _access_token() -> str:
    return get_settings().resolve("docusign_access_token", default="")


def _base_url() -> str:
    return get_settings().resolve("docusign_base_url", default=DEFAULT_BASE_URL)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _acct_url(path: str) -> str:
    return f"{_base_url()}/accounts/{_account_id()}/{path.lstrip('/')}"


# ---------------------------------------------------------------------------
# Internal HTTP
# ---------------------------------------------------------------------------

def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = _acct_url(path) + qs
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = _acct_url(path)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _put(path: str, body: dict) -> dict:
    url = _acct_url(path)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PUT")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------

def list_envelopes(count: int = 10, status: str | None = None) -> list[dict[str, Any]]:
    """List recent envelopes.

    Args:
        count: Max envelopes to return.
        status: Filter by status: 'sent' | 'delivered' | 'completed' | 'declined' | 'voided'

    Returns: List of {envelope_id, status, subject, sent_date, completed_date, recipients}.
    """
    from datetime import datetime, timedelta, timezone
    from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params: dict[str, Any] = {"from_date": from_date, "count": count}
    if status:
        params["status"] = status

    resp = _get("envelopes", params)
    return [
        {
            "envelope_id": e.get("envelopeId"),
            "status": e.get("status"),
            "subject": e.get("emailSubject", ""),
            "sent_date": e.get("sentDateTime", ""),
            "completed_date": e.get("completedDateTime", ""),
        }
        for e in resp.get("envelopes", [])
    ]


def get_envelope(envelope_id: str) -> dict[str, Any]:
    """Get details of a specific envelope including recipient status."""
    resp = _get(f"envelopes/{envelope_id}")
    return {
        "envelope_id": resp.get("envelopeId"),
        "status": resp.get("status"),
        "subject": resp.get("emailSubject", ""),
        "sent_date": resp.get("sentDateTime", ""),
        "completed_date": resp.get("completedDateTime", ""),
        "recipients": resp.get("recipients", {}),
    }


def get_envelope_recipients(envelope_id: str) -> list[dict[str, Any]]:
    """Get all recipient status for an envelope."""
    resp = _get(f"envelopes/{envelope_id}/recipients")
    signers = resp.get("signers", [])
    return [
        {
            "name": s.get("name"),
            "email": s.get("email"),
            "status": s.get("status"),
            "signed_date": s.get("signedDateTime", ""),
            "routing_order": s.get("routingOrder"),
        }
        for s in signers
    ]


def send_envelope_from_template(
    template_id: str,
    signers: list[dict],
    email_subject: str = "Please sign this document",
    email_body: str = "",
) -> dict[str, Any]:
    """Send a document from a saved DocuSign template.

    Args:
        template_id: DocuSign template ID.
        signers: List of {name, email, role_name} — role_name must match template roles.
        email_subject: Subject line of the signing request email.
        email_body: Optional body text.

    Returns: {envelope_id, status, uri}.
    """
    template_roles = [
        {
            "name": s["name"],
            "email": s["email"],
            "roleName": s.get("role_name", "Signer"),
        }
        for s in signers
    ]
    body = {
        "templateId": template_id,
        "templateRoles": template_roles,
        "emailSubject": email_subject,
        "emailBlurb": email_body,
        "status": "sent",
    }
    resp = _post("envelopes", body)
    return {
        "envelope_id": resp.get("envelopeId"),
        "status": resp.get("status"),
        "uri": resp.get("uri"),
    }


def send_envelope_with_document(
    document_bytes: bytes,
    document_name: str,
    signers: list[dict],
    email_subject: str = "Please sign this document",
    sign_here_page: int = 1,
    sign_here_x: int = 100,
    sign_here_y: int = 150,
) -> dict[str, Any]:
    """Send a raw document (PDF) for signature.

    Args:
        document_bytes: PDF content.
        document_name: Filename shown to signers.
        signers: List of {name, email}.
        email_subject: Email subject line.
        sign_here_x/y: Signature tab position in points from bottom-left.

    Returns: {envelope_id, status}.
    """
    doc_b64 = base64.b64encode(document_bytes).decode()
    doc_id = "1"

    recipients_list = []
    for i, signer in enumerate(signers, start=1):
        recipients_list.append({
            "name": signer["name"],
            "email": signer["email"],
            "recipientId": str(i),
            "routingOrder": str(i),
            "tabs": {
                "signHereTabs": [{
                    "documentId": doc_id,
                    "pageNumber": str(sign_here_page),
                    "xPosition": str(sign_here_x),
                    "yPosition": str(sign_here_y),
                }]
            },
        })

    body = {
        "emailSubject": email_subject,
        "status": "sent",
        "documents": [{
            "documentId": doc_id,
            "name": document_name,
            "documentBase64": doc_b64,
            "fileExtension": "pdf",
        }],
        "recipients": {"signers": recipients_list},
    }
    resp = _post("envelopes", body)
    return {
        "envelope_id": resp.get("envelopeId"),
        "status": resp.get("status"),
    }


def void_envelope(envelope_id: str, reason: str = "Voided by ORB Platform") -> bool:
    """Void (cancel) a sent envelope.

    Args:
        envelope_id: The envelope to void.
        reason: Void reason (required by DocuSign).
    """
    try:
        _put(f"envelopes/{envelope_id}", {"status": "voided", "voidedReason": reason})
        return True
    except Exception as e:
        logger.warning("Failed to void envelope: %s", e)
        return False


def get_signed_document_url(envelope_id: str) -> str | None:
    """Get a temporary download URL for the completed signed document.

    Returns: URL string or None if not available.
    """
    try:
        resp = _get(f"envelopes/{envelope_id}/documents/combined")
        return resp.get("url")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def list_templates(count: int = 20) -> list[dict[str, Any]]:
    """List available document templates."""
    resp = _get("templates", {"count": count})
    return [
        {
            "template_id": t.get("templateId"),
            "name": t.get("name"),
            "created": t.get("created"),
            "last_modified": t.get("lastModified"),
        }
        for t in resp.get("envelopeTemplates", [])
    ]


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching account info."""
    try:
        resp = _get("settings")
        return {"success": True, "account_id": _account_id(), "settings_loaded": bool(resp)}
    except Exception as e:
        return {"success": False, "error": str(e)}
