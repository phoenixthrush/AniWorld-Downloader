"""Flask application factory and server entry point."""

import os
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, request, url_for
from flask_wtf.csrf import CSRFProtect

from ..logger import get_logger
from . import db, settings_store, worker
from .version import get_version
from .views import ADMIN_ENDPOINTS, register_blueprints

logger = get_logger(__name__)

DEFAULT_PORT = 8080

# Endpoints that must stay reachable without a session.
_PUBLIC_ENDPOINTS = {
    "static",
    "auth.login",
    "auth.logout",
    "auth.setup",
    "auth.oidc_login",
    "auth.oidc_callback",
}


def _apply_base_url(app):
    """Honour ANIWORLD_WEB_BASE_URL so _external URLs work behind a proxy."""
    base_url = os.environ.get("ANIWORLD_WEB_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return base_url

    parsed = urlparse(base_url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    inner = app.wsgi_app

    def middleware(environ, start_response):
        environ["wsgi.url_scheme"] = scheme
        if host:
            environ["HTTP_HOST"] = host
        return inner(environ, start_response)

    app.wsgi_app = middleware
    return base_url


def _setup_auth(app, base_url, sso_enabled, force_sso):
    from .auth import (
        auth_bp,
        get_or_create_secret_key,
        init_oidc,
        refresh_session_role,
    )

    app.secret_key = get_or_create_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=base_url.startswith("https"),
        PERMANENT_SESSION_LIFETIME=86400,
    )

    csrf = CSRFProtect()
    app.register_blueprint(auth_bp)
    csrf.init_app(app)

    if sso_enabled:
        init_oidc(app, force_sso=force_sso)
    else:
        app.config.update(
            OIDC_ENABLED=False,
            OIDC_DISPLAY_NAME="SSO",
            OIDC_ADMIN_USER=None,
            OIDC_ADMIN_SUBJECT=None,
            FORCE_SSO=False,
        )

    @app.before_request
    def force_first_run_setup():
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return None
        if not app.config.get("FORCE_SSO", False) and not db.has_any_admin():
            return redirect(url_for("auth.setup"))
        return None

    @app.before_request
    def keep_role_fresh():
        return refresh_session_role()

    return csrf


def _protect_endpoints(app, csrf):
    """Wrap every non-public view with a login (or admin) check."""
    from .auth import admin_required, login_required

    for endpoint, view in list(app.view_functions.items()):
        if endpoint in _PUBLIC_ENDPOINTS:
            continue
        guard = admin_required if endpoint in ADMIN_ENDPOINTS else login_required
        app.view_functions[endpoint] = guard(view)

    # JSON APIs are exempt from CSRF tokens: they require an application/json
    # content type, which a cross-origin form cannot send without a preflight.
    for endpoint, view in app.view_functions.items():
        if endpoint.startswith("api.") or endpoint.startswith("auth.admin_"):
            csrf.exempt(view)


def create_app(auth_enabled=False, sso_enabled=False, force_sso=False):
    app = Flask(__name__)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000
    app.config["AUTH_ENABLED"] = auth_enabled

    version = get_version()
    base_url = _apply_base_url(app)

    db.init_db()

    csrf = None
    if auth_enabled:
        csrf = _setup_auth(app, base_url, sso_enabled, force_sso)

    @app.context_processor
    def inject_globals():
        from .auth import get_current_user

        return {
            "app_version": version,
            "auth_enabled": auth_enabled,
            "current_user": get_current_user() if auth_enabled else None,
            "oidc_enabled": app.config.get("OIDC_ENABLED", False),
            "oidc_display_name": app.config.get("OIDC_DISPLAY_NAME", "SSO"),
            "force_sso": app.config.get("FORCE_SSO", False),
            "ui_language": settings_store.ui_language(),
            "library_enabled": settings_store.library_enabled(),
            "github_url": "https://github.com/phoenixthrush/AniWorld-Downloader",
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        if request.path.startswith("/api/"):
            response.headers.setdefault(
                "Cache-Control", "no-store, no-cache, must-revalidate"
            )
        return response

    @app.before_request
    def require_json_body():
        """Block form-encoded writes to the API so they can't bypass CSRF."""
        if request.method not in ("POST", "PUT", "DELETE"):
            return None
        if not request.path.startswith("/api/"):
            return None
        if not request.content_length:
            return None
        if not (request.content_type or "").startswith("application/json"):
            return jsonify({"error": "Content-Type must be application/json"}), 415
        return None

    register_blueprints(app)

    if auth_enabled:
        _protect_endpoints(app, csrf)

    _start_background_services()
    return app


def _start_background_services():
    """Start the queue worker and the Discord bot.

    Flask's reloader runs the factory in both the parent and the child process,
    so in debug mode only the child (the real server) may start them.
    """
    debug = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    if debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    _wire_captcha_hooks()
    worker.ensure_started()
    try:
        from .discord_bot import start_if_enabled

        start_if_enabled()
    except Exception as exc:
        logger.warning("Discord bot not started: %s", exc)


def _wire_captcha_hooks():
    """Let the playwright captcha module report into the queue without importing us."""
    from ..playwright import captcha

    captcha._on_captcha_start = db.set_captcha_url
    captcha._on_captcha_end = db.clear_captcha_url


def start_web_ui(
    host="127.0.0.1",
    port=DEFAULT_PORT,
    open_browser=True,
    auth_enabled=False,
    sso_enabled=False,
    force_sso=False,
):
    import threading
    import webbrowser

    # Env overrides keep Docker deployments configurable without CLI flags
    force_sso = force_sso or os.getenv("ANIWORLD_WEB_FORCE_SSO", "0") == "1"
    sso_enabled = sso_enabled or force_sso or os.getenv("ANIWORLD_WEB_SSO", "0") == "1"
    auth_enabled = (
        auth_enabled or force_sso or os.getenv("ANIWORLD_WEB_AUTH", "0") == "1"
    )

    app = create_app(
        auth_enabled=auth_enabled, sso_enabled=sso_enabled, force_sso=force_sso
    )

    display_host = "localhost" if host == "127.0.0.1" else host
    url = f"http://{display_host}:{port}"
    print(f"Starting AniWorld Web UI on {url}")

    debug = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    # The reloader re-executes this function in a child process, only the parent
    # should open the browser or it opens twice.
    if open_browser and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        serve(app, host=host, port=port)
