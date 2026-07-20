import os
import re
import secrets
import time
from functools import wraps

try:
    from authlib.integrations.flask_client import OAuth

    _SSO_AVAILABLE = True
except ImportError:

    class DummyOAuth:
        def init_app(self, app):
            pass

        def register(self, *args, **kwargs):
            pass

    OAuth = DummyOAuth
    _SSO_AVAILABLE = False

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
from .db import (
    create_user,
    delete_user,
    find_or_create_sso_user,
    get_db,
    has_any_admin,
    list_users,
    update_user_role,
    verify_user,
)

logger = get_logger(__name__)

_SECRET_KEY_PATH = ANIWORLD_CONFIG_DIR / ".flask_secret"

oauth = OAuth()


def get_oidc_config():
    issuer = os.environ.get("ANIWORLD_OIDC_ISSUER_URL", "").strip()
    client_id = os.environ.get("ANIWORLD_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("ANIWORLD_OIDC_CLIENT_SECRET", "").strip()
    if not (issuer and client_id and client_secret):
        return None
    return {
        "issuer_url": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "display_name": os.environ.get("ANIWORLD_OIDC_DISPLAY_NAME", "SSO").strip()
        or "SSO",
        "admin_user": os.environ.get("ANIWORLD_OIDC_ADMIN_USER", "").strip() or None,
        "admin_subject": os.environ.get("ANIWORLD_OIDC_ADMIN_SUBJECT", "").strip()
        or None,
    }


def init_oidc(app, force_sso=False):
    cfg = get_oidc_config()
    if cfg is None:
        app.config["OIDC_ENABLED"] = False
        app.config["OIDC_DISPLAY_NAME"] = "SSO"
        app.config["OIDC_ADMIN_USER"] = None
        app.config["OIDC_ADMIN_SUBJECT"] = None
        app.config["FORCE_SSO"] = force_sso
        return

    if not _SSO_AVAILABLE:
        logger.error(
            "SSO enabled but authlib is not installed. SSO login will be unavailable."
        )
        if force_sso:
            raise RuntimeError("SSO login is forced, but authlib is not installed.")
        app.config["OIDC_ENABLED"] = False
        app.config["OIDC_DISPLAY_NAME"] = "SSO"
        app.config["OIDC_ADMIN_USER"] = None
        app.config["OIDC_ADMIN_SUBJECT"] = None
        app.config["FORCE_SSO"] = False
        return

    oauth.init_app(app)
    oauth.register(
        name="oidc",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        server_metadata_url=cfg["issuer_url"].rstrip("/")
        + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    app.config["OIDC_ENABLED"] = True
    app.config["OIDC_DISPLAY_NAME"] = cfg["display_name"]
    app.config["OIDC_ADMIN_USER"] = cfg["admin_user"]
    app.config["OIDC_ADMIN_SUBJECT"] = cfg["admin_subject"]
    app.config["FORCE_SSO"] = force_sso


def get_or_create_secret_key():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_bytes()
    key = secrets.token_bytes(32)
    fd = os.open(str(_SECRET_KEY_PATH), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def get_current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return {
        "id": uid,
        "username": session.get("user_name", ""),
        "role": session.get("user_role", "user"),
    }


def refresh_session_role():
    """Re-check the user's role from the DB periodically (every 60s)."""
    uid = session.get("user_id")
    if uid is None:
        return None
    last_check = session.get("_role_checked", 0)
    if time.time() - last_check < 60:
        return None
    conn = get_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            session.clear()
            return redirect(url_for("auth.login"))
        session["user_role"] = row["role"]
        session["_role_checked"] = time.time()
    finally:
        conn.close()
    return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user_id") is None:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user_id") is None:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("auth.login"))
        if session.get("user_role") != "admin":
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "admin access required"}), 403
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    force_sso = current_app.config.get("FORCE_SSO", False)
    oidc_enabled = current_app.config.get("OIDC_ENABLED", False)
    oidc_display_name = current_app.config.get("OIDC_DISPLAY_NAME", "SSO")

    if not force_sso and not has_any_admin():
        return redirect(url_for("auth.setup"))

    error = None
    if request.method == "POST" and not force_sso:
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user, err = verify_user(username, password)
        if user:
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_name"] = user["username"]
            session["user_role"] = user["role"]
            return redirect(url_for("index"))
        error = err

    return render_template(
        "login.html",
        error=error,
        oidc_enabled=oidc_enabled,
        oidc_display_name=oidc_display_name,
        force_sso=force_sso,
    )


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if current_app.config.get("FORCE_SSO", False):
        return redirect(url_for("auth.login"))

    if has_any_admin():
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        if not username:
            error = "Username is required."
        elif len(username) > 64:
            error = "Username must be at most 64 characters."
        elif not re.match(r"^[a-zA-Z0-9._-]+$", username):
            error = "Username may only contain letters, digits, dots, hyphens, and underscores."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            uid = create_user(username, password, role="admin")
            session.permanent = True
            session["user_id"] = uid
            session["user_name"] = username
            session["user_role"] = "admin"
            return redirect(url_for("index"))

    return render_template("setup.html", error=error)


# ---------------------------------------------------------------------------
# OIDC routes
# ---------------------------------------------------------------------------


@auth_bp.route("/oidc/login")
def oidc_login():
    if not current_app.config.get("OIDC_ENABLED", False):
        return redirect(url_for("auth.login"))
    try:
        nonce = secrets.token_urlsafe(32)
        session["oidc_nonce"] = nonce
        redirect_uri = url_for("auth.oidc_callback", _external=True)
        return oauth.oidc.authorize_redirect(redirect_uri, nonce=nonce)
    except Exception:
        logger.exception("SSO provider unavailable")
        return render_template(
            "login.html",
            error="SSO provider is currently unavailable. Please try again later.",
            oidc_enabled=current_app.config.get("OIDC_ENABLED", False),
            oidc_display_name=current_app.config.get("OIDC_DISPLAY_NAME", "SSO"),
            force_sso=current_app.config.get("FORCE_SSO", False),
        )


@auth_bp.route("/oidc/callback")
def oidc_callback():
    if not current_app.config.get("OIDC_ENABLED", False):
        return redirect(url_for("auth.login"))

    try:
        token = oauth.oidc.authorize_access_token()
        nonce = session.pop("oidc_nonce", None)
        userinfo = token.get("userinfo")
        if userinfo is None:
            userinfo = oauth.oidc.parse_id_token(token, nonce=nonce)

        subject = userinfo.get("sub", "")
        username = (
            userinfo.get("preferred_username") or userinfo.get("email") or subject
        )
        username = re.sub(r"[^a-zA-Z0-9._-]", "_", username)

        issuer = userinfo.get("iss", "")
        if not issuer:
            cfg = get_oidc_config()
            issuer = cfg["issuer_url"] if cfg else ""

        admin_username = current_app.config.get("OIDC_ADMIN_USER")
        admin_subject = current_app.config.get("OIDC_ADMIN_SUBJECT")

        user = find_or_create_sso_user(
            issuer=issuer,
            subject=subject,
            username=username,
            admin_username=admin_username,
            admin_subject=admin_subject,
        )

        logger.info(
            "SSO login: user=%s subject=%s issuer=%s", username, subject, issuer
        )

        session.permanent = True
        session["user_id"] = user["id"]
        session["user_name"] = user["username"]
        session["user_role"] = user["role"]
        return redirect(url_for("index"))

    except ValueError as e:
        return render_template(
            "login.html",
            error=str(e),
            oidc_enabled=current_app.config.get("OIDC_ENABLED", False),
            oidc_display_name=current_app.config.get("OIDC_DISPLAY_NAME", "SSO"),
            force_sso=current_app.config.get("FORCE_SSO", False),
        )
    except Exception:
        logger.exception("SSO login failed")
        return render_template(
            "login.html",
            error="SSO login failed. Please try again or contact an administrator.",
            oidc_enabled=current_app.config.get("OIDC_ENABLED", False),
            oidc_display_name=current_app.config.get("OIDC_DISPLAY_NAME", "SSO"),
            force_sso=current_app.config.get("FORCE_SSO", False),
        )


# ---------------------------------------------------------------------------
# Admin dashboard + API
# ---------------------------------------------------------------------------


@auth_bp.route("/admin")
@admin_required
def admin_dashboard():
    return redirect(url_for("settings_page"))


@auth_bp.route("/admin/api/users")
@admin_required
def admin_list_users():
    return jsonify({"users": list_users()})


@auth_bp.route("/admin/api/users", methods=["POST"])
@admin_required
def admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role", "user")

    if not username:
        return jsonify({"error": "Username is required"}), 400
    if len(username) > 64:
        return jsonify({"error": "Username must be at most 64 characters"}), 400
    if not re.match(r"^[a-zA-Z0-9._-]+$", username):
        return jsonify(
            {
                "error": "Username may only contain letters, digits, dots, hyphens, and underscores"
            }
        ), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in ("admin", "user"):
        return jsonify({"error": "Invalid role"}), 400

    try:
        uid = create_user(username, password, role)
        return jsonify({"id": uid, "username": username, "role": role})
    except Exception as e:
        return jsonify({"error": str(e)}), 409


@auth_bp.route("/admin/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"error": "Cannot delete your own account"}), 400
    ok, err = delete_user(user_id)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@auth_bp.route("/admin/api/users/<int:user_id>/role", methods=["PUT"])
@admin_required
def admin_update_role(user_id):
    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "")
    ok, err = update_user_role(user_id, new_role)
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})
