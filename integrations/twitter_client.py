"""Twitter / X API v2 client for ORB Platform.

Agents can use Twitter/X to:
  - Post tweets from a connected account
  - Reply to mentions and threads
  - Search recent tweets (for market intel or brand monitoring)
  - Like / retweet / bookmark posts
  - Get account analytics

Requires:
  TWITTER_BEARER_TOKEN     — App-only Bearer Token (read-only access)
  TWITTER_API_KEY          — API Key (consumer key)
  TWITTER_API_SECRET       — API Secret (consumer secret)
  TWITTER_ACCESS_TOKEN     — OAuth 1.0a Access Token (for write operations)
  TWITTER_ACCESS_SECRET    — OAuth 1.0a Access Token Secret

Docs: https://developer.twitter.com/en/docs/twitter-api
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import urllib.request
import uuid
from typing import Any

from config.settings import get_settings

logger = logging.getLogger("orb.integrations.twitter")

TWITTER_URL = "https://api.twitter.com/2"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def is_twitter_available() -> bool:
    s = get_settings()
    return bool(s.resolve("twitter_bearer_token", default="") or s.resolve("twitter_api_key", default=""))


def _bearer_token() -> str:
    return get_settings().resolve("twitter_bearer_token", default="")


def _api_key() -> str:
    return get_settings().resolve("twitter_api_key", default="")


def _api_secret() -> str:
    return get_settings().resolve("twitter_api_secret", default="")


def _access_token() -> str:
    return get_settings().resolve("twitter_access_token", default="")


def _access_secret() -> str:
    return get_settings().resolve("twitter_access_secret", default="")


# ---------------------------------------------------------------------------
# OAuth 1.0a signing (required for write operations)
# ---------------------------------------------------------------------------

def _oauth1_header(method: str, url: str, body_params: dict | None = None) -> str:
    """Generate an OAuth 1.0a Authorization header."""
    params = body_params or {}
    oauth_params = {
        "oauth_consumer_key": _api_key(),
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": _access_token(),
        "oauth_version": "1.0",
    }
    all_params = {**params, **oauth_params}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base_string = (
        f"{method.upper()}&"
        f"{urllib.parse.quote(url, safe='')}&"
        f"{urllib.parse.quote(sorted_params, safe='')}"
    )
    signing_key = (
        f"{urllib.parse.quote(_api_secret(), safe='')}&"
        f"{urllib.parse.quote(_access_secret(), safe='')}"
    )
    sig = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = sig

    header_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


def _bearer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_bearer_token()}", "Content-Type": "application/json"}


def _oauth_headers(method: str, url: str) -> dict[str, str]:
    return {
        "Authorization": _oauth1_header(method, url),
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Read operations (Bearer token — no user context needed)
# ---------------------------------------------------------------------------

def search_tweets(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search recent tweets.

    Args:
        query: Search query (supports operators: from:, to:, #hashtag, -exclude)
        max_results: Number of results (10–100).

    Returns: List of {id, text, author_id, created_at, metrics}.
    """
    params = {
        "query": query,
        "max_results": min(max(max_results, 10), 100),
        "tweet.fields": "created_at,author_id,public_metrics",
    }
    qs = urllib.parse.urlencode(params)
    url = f"{TWITTER_URL}/tweets/search/recent?{qs}"
    req = urllib.request.Request(url, headers=_bearer_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return [
        {
            "id": t.get("id"),
            "text": t.get("text", ""),
            "author_id": t.get("author_id"),
            "created_at": t.get("created_at"),
            "likes": t.get("public_metrics", {}).get("like_count", 0),
            "retweets": t.get("public_metrics", {}).get("retweet_count", 0),
            "replies": t.get("public_metrics", {}).get("reply_count", 0),
        }
        for t in data.get("data", [])
    ]


def get_user_by_username(username: str) -> dict[str, Any]:
    """Get a Twitter user's profile by username.

    Args:
        username: Twitter handle without '@'.
    """
    qs = urllib.parse.urlencode({
        "user.fields": "id,name,username,description,public_metrics,verified"
    })
    url = f"{TWITTER_URL}/users/by/username/{username}?{qs}"
    req = urllib.request.Request(url, headers=_bearer_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("data", data)


def get_user_tweets(user_id: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Get recent tweets from a user (by user ID)."""
    qs = urllib.parse.urlencode({
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics",
    })
    url = f"{TWITTER_URL}/users/{user_id}/tweets?{qs}"
    req = urllib.request.Request(url, headers=_bearer_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("data", [])


# ---------------------------------------------------------------------------
# Write operations (OAuth 1.0a — requires user-level tokens)
# ---------------------------------------------------------------------------

def post_tweet(text: str, reply_to_id: str | None = None) -> dict[str, Any]:
    """Post a tweet from the connected account.

    Args:
        text: Tweet content (max 280 chars).
        reply_to_id: Tweet ID to reply to (optional).

    Returns: Created tweet {id, text}.
    """
    url = f"{TWITTER_URL}/tweets"
    body: dict[str, Any] = {"text": text[:280]}
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_oauth_headers("POST", url), method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    return result.get("data", result)


def delete_tweet(tweet_id: str) -> bool:
    """Delete a tweet by ID."""
    url = f"{TWITTER_URL}/tweets/{tweet_id}"
    req = urllib.request.Request(url, headers=_oauth_headers("DELETE", url), method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    return result.get("data", {}).get("deleted", False)


def like_tweet(tweet_id: str, user_id: str) -> bool:
    """Like a tweet.

    Args:
        tweet_id: Tweet to like.
        user_id: Authenticated user's ID.
    """
    url = f"{TWITTER_URL}/users/{user_id}/likes"
    body = {"tweet_id": tweet_id}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_oauth_headers("POST", url), method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    return result.get("data", {}).get("liked", False)


# ---------------------------------------------------------------------------
# Account info
# ---------------------------------------------------------------------------

def get_me() -> dict[str, Any]:
    """Get the authenticated user's profile (requires user context token)."""
    url = f"{TWITTER_URL}/users/me?user.fields=id,name,username,public_metrics"
    req = urllib.request.Request(url, headers=_oauth_headers("GET", url), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data.get("data", data)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection() -> dict[str, Any]:
    """Test by fetching the authenticated account or verifying Bearer token."""
    try:
        if _access_token():
            me = get_me()
            return {"success": True, "username": me.get("username"), "name": me.get("name")}
        elif _bearer_token():
            results = search_tweets("from:Twitter", max_results=1)
            return {"success": True, "mode": "read-only (Bearer token)"}
        else:
            return {"success": False, "error": "No Twitter credentials configured."}
    except Exception as e:
        return {"success": False, "error": str(e)}
