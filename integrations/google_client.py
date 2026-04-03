"""Google API OAuth2 client for ORB.

Handles credential management for Gmail and Google Calendar.
Owner authorizes once via browser; token is saved to disk and auto-refreshed.

Setup flow:
  1. Owner calls GET /aria/google/authorize → gets auth URL
  2. Owner visits URL, signs in with Google, grants permissions
  3. Google redirects to google_redirect_uri with ?code=...
  4. Owner pastes code to POST /aria/google/connect → token saved
  5. All future briefings include Gmail + Calendar data automatically
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from jose import JWTError, jwt

from app.database.settings_store import SettingsStore
from config.settings import get_settings

# Token file written here after first authorization
TOKEN_PATH = Path(__file__).resolve().parent.parent / "config" / "google_token.json"

# Scopes: read Gmail + read Calendar (no write access needed)
SCOPES = [
	"https://www.googleapis.com/auth/gmail.readonly",
	"https://www.googleapis.com/auth/gmail.compose",
	"https://www.googleapis.com/auth/calendar.readonly",
	"https://www.googleapis.com/auth/calendar.events",
	"https://www.googleapis.com/auth/contacts.readonly",
]

_OAUTH_TOKEN_KEY_PREFIX = "google_oauth_tokens"


def _build_client_config() -> dict[str, Any]:
	"""Build OAuth2 client config dict from ORB settings."""
	s = get_settings()
	return {
		"web": {
			"client_id": s.google_client_id,
			"client_secret": s.google_client_secret,
			"redirect_uris": [s.google_redirect_uri],
			"auth_uri": "https://accounts.google.com/o/oauth2/auth",
			"token_uri": "https://oauth2.googleapis.com/token",
		}
	}


def get_credentials() -> Optional[Credentials]:
	"""
	Load stored OAuth2 credentials from disk, refreshing the token if expired.
	Returns None when the token file does not exist (owner not yet authorized).
	"""
	if not TOKEN_PATH.exists():
		return None

	try:
		creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
	except Exception:
		return None

	if creds and creds.expired and creds.refresh_token:
		try:
			creds.refresh(Request())
			_save_credentials(creds)
		except Exception:
			return None

	return creds if (creds and creds.valid) else None


def _save_credentials(creds: Credentials) -> None:
	"""Persist credentials JSON to TOKEN_PATH."""
	TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
	TOKEN_PATH.write_text(creds.to_json())


def is_authorized() -> bool:
	"""Return True when valid Google credentials are on disk."""
	return get_credentials() is not None


def get_auth_url(owner_id: str | None = None) -> str:
	"""
	Generate the OAuth2 authorization URL for the owner to visit.
	The URL redirects to google_redirect_uri after the owner approves.
	"""
	s = get_settings()
	state = _encode_state(owner_id) if owner_id else None
	flow = Flow.from_client_config(
		_build_client_config(),
		scopes=SCOPES,
		redirect_uri=s.google_redirect_uri,
	)
	auth_url, _ = flow.authorization_url(
		access_type="offline",
		include_granted_scopes="true",
		prompt="consent",
		state=state,
	)
	return auth_url


def exchange_code(code: str) -> dict[str, Any]:
	"""
	Exchange an authorization code for credentials and persist them.

	Returns:
		{"success": True, "email": "owner@gmail.com"}
		{"success": False, "error": "...description..."}
	"""
	s = get_settings()
	try:
		flow = Flow.from_client_config(
			_build_client_config(),
			scopes=SCOPES,
			redirect_uri=s.google_redirect_uri,
		)
		flow.fetch_token(code=code)
		creds = flow.credentials
		_save_credentials(creds)

		email = _get_authorized_email(creds)
		return {"success": True, "email": email}
	except Exception as exc:
		return {"success": False, "error": str(exc)}


def _get_authorized_email(creds: Credentials) -> str:
	"""Resolve the email address of the authorized Google account."""
	try:
		service = build("oauth2", "v2", credentials=creds)
		info = service.userinfo().get().execute()
		return info.get("email", "")
	except Exception:
		return ""


def get_gmail_service():
	"""
	Build a Gmail API service client from stored credentials.
	Returns None if no valid credentials exist.
	"""
	creds = get_credentials()
	if not creds:
		return None
	try:
		return build("gmail", "v1", credentials=creds)
	except Exception:
		return None


def get_calendar_service():
	"""
	Build a Google Calendar API service client from stored credentials.
	Returns None if no valid credentials exist.
	"""
	creds = get_credentials()
	if not creds:
		return None
	try:
		return build("calendar", "v3", credentials=creds)
	except Exception:
		return None


def _encode_state(owner_id: str) -> str:
	"""Encode owner_id in OAuth state token to prevent tampering."""
	s = get_settings()
	now = datetime.now(timezone.utc)
	payload = {
		"owner_id": owner_id,
		"iat": int(now.timestamp()),
		"exp": int((now + timedelta(minutes=20)).timestamp()),
	}
	return jwt.encode(payload, s.jwt_secret_key, algorithm="HS256")


def _decode_state(state: str) -> str:
	"""Decode OAuth state token and return owner_id."""
	s = get_settings()
	try:
		payload = jwt.decode(state, s.jwt_secret_key, algorithms=["HS256"])
	except JWTError as exc:
		raise ValueError("Invalid Google OAuth state token.") from exc

	owner_id = str(payload.get("owner_id") or "").strip()
	if not owner_id:
		raise ValueError("OAuth state token missing owner context.")
	return owner_id


def _owner_token_key(owner_id: str) -> str:
	return f"{_OAUTH_TOKEN_KEY_PREFIX}:{owner_id}"


def _credentials_to_record(creds: Credentials, email: str = "") -> dict[str, Any]:
	return {
		"token": creds.token,
		"refresh_token": creds.refresh_token,
		"token_uri": creds.token_uri,
		"client_id": creds.client_id,
		"client_secret": creds.client_secret,
		"scopes": list(creds.scopes or SCOPES),
		"expiry": creds.expiry.isoformat() if creds.expiry else None,
		"email": email,
		"updated_at": datetime.now(timezone.utc).isoformat(),
	}


def _record_to_credentials(record: dict[str, Any]) -> Credentials:
	creds = Credentials.from_authorized_user_info(record, SCOPES)
	expiry_raw = record.get("expiry")
	if expiry_raw:
		try:
			creds.expiry = datetime.fromisoformat(str(expiry_raw).replace("Z", "+00:00"))
		except Exception:
			pass
	return creds


def _load_owner_record(owner_id: str) -> dict[str, Any] | None:
	store = SettingsStore()
	raw = store.get(_owner_token_key(owner_id), default="")
	if not raw:
		return None
	try:
		parsed = json.loads(raw)
		return parsed if isinstance(parsed, dict) else None
	except Exception:
		return None


def _save_owner_record(owner_id: str, record: dict[str, Any]) -> None:
	store = SettingsStore()
	store.save(
		key=_owner_token_key(owner_id),
		value=json.dumps(record),
		description="Google OAuth token bundle",
		category="google",
		owner_id=owner_id,
	)


def is_owner_authorized(owner_id: str) -> bool:
	"""Return True when the owner has valid OAuth tokens stored."""
	try:
		refresh_token_if_needed(owner_id)
		return True
	except Exception:
		return False


def get_owner_email(owner_id: str) -> str:
	"""Return connected Google email for owner when available."""
	record = _load_owner_record(owner_id)
	if not record:
		return ""
	return str(record.get("email") or "")


def handle_callback(code: str, state: str) -> dict[str, Any]:
	"""Exchange code for tokens, persist encrypted token bundle, and return owner context."""
	owner_id = _decode_state(state)
	s = get_settings()
	flow = Flow.from_client_config(
		_build_client_config(),
		scopes=SCOPES,
		redirect_uri=s.google_redirect_uri,
	)
	flow.fetch_token(code=code)
	creds = flow.credentials
	email = _get_authorized_email(creds)
	_save_owner_record(owner_id, _credentials_to_record(creds, email=email))
	return {"success": True, "owner_id": owner_id, "email": email}


def refresh_token_if_needed(owner_id: str) -> str:
	"""Return a valid access token for owner, refreshing and persisting as needed."""
	record = _load_owner_record(owner_id)
	if not record:
		raise ValueError("Google is not connected for this owner.")

	creds = _record_to_credentials(record)
	if creds.expired and creds.refresh_token:
		creds.refresh(Request())
		record = {
			**record,
			**_credentials_to_record(creds, email=str(record.get("email") or "")),
		}
		_save_owner_record(owner_id, record)

	if not creds.token:
		raise ValueError("Google token unavailable after refresh.")
	return str(creds.token)


def disconnect_owner(owner_id: str) -> bool:
	"""Delete owner-scoped Google OAuth bundle from encrypted settings store."""
	store = SettingsStore()
	return store.delete(_owner_token_key(owner_id))
