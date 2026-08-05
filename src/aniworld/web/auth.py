"""Optional authentication: local accounts and OIDC single sign-on.

Only wired up when the web UI is started with --web-auth / --web-sso.
"""

import os
import re
import secrets
import time
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..config import ANIWORLD_CONFIG_DIR
from ..logger import get_logger
from . import db

logger = get_logger(__name__)

try:
    from authlib.integrations.flask_client import OAuth

    SSO_AVAILABLE = True
except ImportError:  # authlib is an optional extra

    class OAuth:  # type: ignore[no-redef]
        def init_app(self, app):
            pass

        def register(self, *args, **kwargs):
            pass

    SSO_AVAILABLE = False

oauth = OAuth()

_SECRET_KEY_PATH = ANIWORLD_CONFIG_DIR / ".flask_secret"

USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
MIN_PASSWORD_LENGTH = 8

# How often a logged-in session re-reads its role from the database.
ROLE_REFRESH_SECONDS = 60

auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def get_or_create_secret_key():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_bytes()
    key = secrets.token_bytes(32)
    handle = os.open(str(_SECRET_KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(handle, key)
    finally:
        os.close(handle)
    return key


def oidc_config():
    issuer = os.environ.get("ANIWORLD_OIDC_ISSUER_URL", "").strip()
    client_id = os.environ.get("ANIWORLD_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ANIWORLD_OIDC_CLIENT_SECRET", "").strip()
    if not (issuer and client_id and client_secret):
        return None
    return {
        "issuer_url": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "display_name": os.environ.get("ANIWORLD_OIDC_DISPLAY_NAME", "").strip() or "SSO",
        "admin_user": os.environ.get("ANIWORLD_OIDC_ADMIN_USER", "").strip() or None,
        "admin_subject": os.environ.get("ANIWORLD_OIDC_ADMIN_SUBJECT", "").strip() or None,
    }


def _disable_oidc(app, force_sso=False):
    app.config.update(
        OIDC_ENABLED=False,
        OIDC_DISPLAY_NAME="SSO",
        OIDC_ADMIN_USER=None,
        OIDC_ADMIN_SUBJECT=None,
        FORCE_SSO=force_sso,
    )


def init_oidc(app, force_sso=False):
    config = oidc_config()
    if config is None:
        _disable_oidc(app, force_sso)
        return

    if not SSO_AVAILABLE:
        if force_sso:
            raise RuntimeError("SSO login is forced, but authlib is not installed.")
        logger.error("SSO enabled but authlib is not installed, SSO login is unavailable")
        _disable_oidc(app)
        return

    oauth.init_app(app)
    oauth.register(
        name="oidc",
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        server_metadata_url=config["issuer_url"].rstrip("/")
        + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    app.config.update(
        OIDC_ENABLED=True,
        OIDC_DISPLAY_NAME=config["display_name"],
        OIDC_ADMIN_USER=config["admin_user"],
        OIDC_ADMIN_SUBJECT=config["admin_subject"],
        FORCE_SSO=force_sso,
    )


def _login_view_context(error=None):
    return {
        "error": error,
        "oidc_enabled": current_app.config.get("OIDC_ENABLED", False),
        "oidc_display_name": current_app.config.get("OIDC_DISPLAY_NAME", "SSO"),
        "force_sso": current_app.config.get("FORCE_SSO", False),
    }


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def get_current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return {
        "id": user_id,
        "username": session.get("user_name", ""),
        "role": session.get("user_role", "user"),
    }


def current_username():
    user = get_current_user()
    return user["username"] if user else None


def _sign_in(user):
    session.permanent = True
    session["user_id"] = user["id"]
    session["user_name"] = user["username"]
    session["user_role"] = user["role"]
    session["_role_checked"] = time.time()


def refresh_session_role():
    """Pick up role changes (and deleted accounts) without a re-login."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    if time.time() - session.get("_role_checked", 0) < ROLE_REFRESH_SECONDS:
        return None

    user = db.get_user(user_id)
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
    session["user_role"] = user["role"]
    session["_role_checked"] = time.time()
    return None


def _wants_json():
    return request.is_json or request.path.startswith("/api/")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            if _wants_json():
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            if _wants_json():
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("auth.login"))
        if session.get("user_role") != "admin":
            if _wants_json():
                return jsonify({"error": "admin access required"}), 403
            return redirect(url_for("pages.index"))
        return view(*args, **kwargs)

    return wrapper


def _validate_account(username, password):
    if not username:
        return "Username is required."
    if len(username) > 64:
        return "Username must be at most 64 characters."
    if not USERNAME_RE.match(username):
        return "Username may only contain letters, digits, dots, hyphens and underscores."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


# ---------------------------------------------------------------------------
# Local login
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    force_sso = current_app.config.get("FORCE_SSO", False)
    if not force_sso and not db.has_any_admin():
        return redirect(url_for("auth.setup"))

    error = None
    if request.method == "POST" and not force_sso:
        user = db.verify_user(
            (request.form.get("username") or "").strip(),
            request.form.get("password") or "",
        )
        if user:
            _sign_in(user)
            return redirect(url_for("pages.index"))
        error = "Invalid username or password."

    return render_template("login.html", **_login_view_context(error))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if current_app.config.get("FORCE_SSO", False) or db.has_any_admin():
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        error = _validate_account(username, password)
        if not error and password != (request.form.get("confirm") or ""):
            error = "Passwords do not match."
        if not error:
            user_id = db.create_user(username, password, role="admin")
            _sign_in({"id": user_id, "username": username, "role": "admin"})
            return redirect(url_for("pages.index"))

    return render_template("setup.html", error=error)


# ---------------------------------------------------------------------------
# OIDC
# ---------------------------------------------------------------------------
@auth_bp.route("/oidc/login")
def oidc_login():
    if not current_app.config.get("OIDC_ENABLED", False):
        return redirect(url_for("auth.login"))
    try:
        nonce = secrets.token_urlsafe(32)
        session["oidc_nonce"] = nonce
        return oauth.oidc.authorize_redirect(
            url_for("auth.oidc_callback", _external=True), nonce=nonce
        )
    except Exception:
        logger.exception("SSO provider unavailable")
        return render_template(
            "login.html",
            **_login_view_context("SSO provider is currently unavailable."),
        )


@auth_bp.route("/oidc/callback")
def oidc_callback():
    if not current_app.config.get("OIDC_ENABLED", False):
        return redirect(url_for("auth.login"))

    try:
        token = oauth.oidc.authorize_access_token()
        nonce = session.pop("oidc_nonce", None)
        userinfo = token.get("userinfo") or oauth.oidc.parse_id_token(token, nonce=nonce)

        subject = userinfo.get("sub", "")
        raw_name = (
            userinfo.get("preferred_username") or userinfo.get("email") or subject
        )
        username = re.sub(r"[^a-zA-Z0-9._-]", "_", raw_name)
        issuer = userinfo.get("iss") or (oidc_config() or {}).get("issuer_url", "")

        user = db.find_or_create_sso_user(
            subject=subject,
            issuer=issuer,
            username=username,
            admin_user=current_app.config.get("OIDC_ADMIN_USER"),
            admin_subject=current_app.config.get("OIDC_ADMIN_SUBJECT"),
        )
        logger.info("SSO login: user=%s issuer=%s", username, issuer)
        _sign_in(user)
        return redirect(url_for("pages.index"))
    except Exception:
        logger.exception("SSO login failed")
        return render_template(
            "login.html",
            **_login_view_context("SSO login failed. Please try again."),
        )


# ---------------------------------------------------------------------------
# User management API (rendered on the settings page)
# ---------------------------------------------------------------------------
@auth_bp.route("/admin/api/users")
@admin_required
def admin_list_users():
    return jsonify({"users": db.list_users()})


@auth_bp.route("/admin/api/users", methods=["POST"])
@admin_required
def admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role", "user")

    error = _validate_account(username, password)
    if error:
        return jsonify({"error": error}), 400
    if role not in ("admin", "user"):
        return jsonify({"error": "Invalid role"}), 400

    try:
        user_id = db.create_user(username, password, role)
    except Exception:
        return jsonify({"error": "That username is already taken"}), 409
    return jsonify({"id": user_id, "username": username, "role": role})


@auth_bp.route("/admin/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"error": "Cannot delete your own account"}), 400
    ok, error = db.delete_user(user_id)
    return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": error}), 400)


@auth_bp.route("/admin/api/users/<int:user_id>/role", methods=["PUT"])
@admin_required
def admin_update_role(user_id):
    data = request.get_json(silent=True) or {}
    ok, error = db.update_user_role(user_id, data.get("role", ""))
    return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": error}), 400)
