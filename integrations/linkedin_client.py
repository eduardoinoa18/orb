"""LinkedIn API client for ORB Platform.

Agents can use LinkedIn to:
  - Post content to your company page or personal profile
  - Get engagement metrics on recent posts
  - Search for people/companies (via LinkedIn Search APIs)
  - Send connection requests (via LinkedIn Messaging, if permissions allow)

Note: LinkedIn's API is restrictive. Most actions require specific
partnership-level access. The functions here use what's available on the
Marketing Developer Platform and basic member/organization APIs.

Requires:
  LINKEDIN_ACCESS_TOKEN    — OAuth 2.0 access token with r_liteprofile,
                             r_emailaddress, w_member_social permissions
  LINKEDIN_ORGANIZATION_ID — LinkedIn Organization/Company ID (if posting to a page)

Docs: https://docs.microsoft.com/en-us/linkedin/
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.linkedin")

BASE_URL = "https://api.linkedin.com/v2"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_linkedin_available() -> bool:
    s = get_settings()
    return bool(s.resolve("linkedin_access_token", default=""))


def _token() -> str:
    return get_settings().resolve("linkedin_access_token", default="")


def _org_id() -> str:
    return get_settings().resolve("linkedin_organization_id", default="")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE_URL}/{path.lstrip('/')}{qs}"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def get_profile() -> dict[str, Any]:
    """Get the authenticated member's profile (lite version)."""
    return _get("me")


def get_email() -> str:
    """Get the authenticated member's primary email."""
    resp = _get("emailAddress", {
        "q": "members",
        "projection": "(elements*(handle~))",
    })
    elements = resp.get("elements", [])
    if elements:
        return elements[0].get("handle~", {}).get("emailAddress", "")
    return ""


# ---------------------------------------------------------------------------
# Posts (UGC — User Generated Content)
# ---------------------------------------------------------------------------

def _author_urn() -> str:
    """Build author URN — organization if set, otherwise member."""
    org = _org_id()
    if org:
        return f"urn:li:organization:{org}"
    # Fall back to person URN
    profile = get_profile()
    return f"urn:li:person:{profile.get('id', '')}"


def post_text(text: str) -> dict[str, Any]:
    """Post a text-only update to LinkedIn.

    Args:
        text: Post content (max 3,000 chars).

    Returns: Created post URN.
    """
    body = {
        "author": _author_urn(),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    return _post("ugcPosts", body)


def post_with_link(text: str, url: str, title: str = "", description: str = "") -> dict[str, Any]:
    """Post an update with a link card.

    Args:
        text: Post caption.
        url: URL to share.
        title: Link card title (optional).
        description: Link card description (optional).
    """
    body = {
        "author": _author_urn(),
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text[:3000]},
                "shareMediaCategory": "ARTICLE",
                "media": [{
                    "status": "READY",
                    "description": {"text": description[:256]},
                    "originalUrl": url,
                    "title": {"text": title[:200]},
                }],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    return _post("ugcPosts", body)


# ---------------------------------------------------------------------------
# Post engagement
# ---------------------------------------------------------------------------

def get_post_stats(post_urn: str) -> dict[str, Any]:
    """Get like/comment/share counts for a post.

    Args:
        post_urn: Post URN from post_text() response e.g. 'urn:li:ugcPost:...'
    """
    encoded = urllib.parse.quote(post_urn, safe="")
    try:
        resp = _get(f"socialActions/{encoded}")
        return {
            "likes": resp.get("likesSummary", {}).get("totalLikes", 0),
            "comments": resp.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
        }
    except Exception as e:
        logger.debug("Could not get LinkedIn post stats: %s", e)
        return {}


def get_recent_posts(count: int = 10) -> list[dict[str, Any]]:
    """Get recent posts from the authenticated author.

    Returns: List of {id, text_preview, created_at, visibility}.
    """
    author = _author_urn()
    resp = _get("ugcPosts", {
        "q": "authors",
        "authors": f"List({urllib.parse.quote(author)})",
        "count": count,
    })
    items = resp.get("elements", [])
    return [
        {
            "id": p.get("id"),
            "text": (p.get("specificContent", {})
                      .get("com.linkedin.ugc.ShareContent", {})
                      .get("shareCommentary", {})
                      .get("text", ""))[:200],
            "created_at": p.get("created", {}).get("time", 0),
            "state": p.get("lifecycleState"),
        }
        for p in items
    ]


# ---------------------------------------------------------------------------
# Organization / Company page
# ---------------------------------------------------------------------------

def get_organization() -> dict[str, Any]:
    """Get the configured LinkedIn organization/company page."""
    org = _org_id()
    if not org:
        return {}
    return _get(f"organizations/{org}")


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the authenticated member profile."""
    try:
        profile = get_profile()
        return {
            "success": True,
            "id": profile.get("id"),
            "first_name": profile.get("localizedFirstName"),
            "last_name": profile.get("localizedLastName"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
