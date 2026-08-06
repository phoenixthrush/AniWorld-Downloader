"""API keys for scripted access to the JSON API.

A key is sent as an X-API-Key header (Authorization: Bearer also works) and
replaces the login session for /api/ requests. Only a sha256 hash is stored,
the plain key is shown once when it is created. sha256 is enough here because
the key is 32 random bytes, not a user chosen password.
"""

import hashlib
import secrets

from flask import g, jsonify, request

from . import db

HEADER = "X-API-Key"
KEY_PREFIX = "awd_"

# read  -> GET only
# write -> everything a normal user can do (search, download, queue)
# admin -> also settings, custom paths, auto-sync and library deletes
SCOPES = ("read", "write", "admin")

# POST endpoints that do not change anything, a read key may still use them.
_READ_SAFE = {"api.search"}

# Minting or revoking keys always needs a real login, never another key.
_SESSION_ONLY = {"api.list_api_keys", "api.create_api_key", "api.delete_api_key"}


def generate():
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def current():
    """The key record for this request, or None when a session is used."""
    return getattr(g, "api_key", None)


def _from_request():
    key = (request.headers.get(HEADER) or "").strip()
    if key:
        return key
    header = (request.headers.get("Authorization") or "").strip()
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return ""


def authenticate(admin_endpoints):
    """Resolve the key header and check its scope. Returns a response on refusal."""
    g.api_key = None
    if not request.path.startswith("/api/"):
        return None

    raw = _from_request()
    if not raw:
        return None

    record = db.verify_api_key(hash_key(raw))
    if not record:
        return jsonify({"error": "Invalid or expired API key"}), 401

    if request.endpoint in _SESSION_ONLY:
        return jsonify({"error": "API keys cannot manage API keys"}), 403

    scope = record["scope"]
    if scope != "admin" and request.endpoint in admin_endpoints:
        return jsonify({"error": "This endpoint needs a key with full access"}), 403
    if (
        scope == "read"
        and request.method not in ("GET", "HEAD", "OPTIONS")
        and request.endpoint not in _READ_SAFE
    ):
        return jsonify({"error": "This key is read only"}), 403

    g.api_key = record
    db.touch_api_key(record["id"])
    return None
