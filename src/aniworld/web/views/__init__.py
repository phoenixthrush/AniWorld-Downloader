"""Blueprint registration.

Pages live under `pages.*`, everything JSON under `api.*`. The `api.` prefix is
what the auth layer uses to decide CSRF exemption, so keep it.
"""

from flask import Blueprint

from . import api_autosync, api_library, api_media, api_queue, api_settings, pages

# Endpoints that need an admin account rather than just a login.
ADMIN_ENDPOINTS = {
    "pages.settings",
    "api.get_settings",
    "api.update_settings",
    "api.public_ip",
    "api.discord_status",
    "api.add_custom_path",
    "api.update_custom_path",
    "api.delete_custom_path",
    "api.delete_library_item",
    "pages.autosync",
    "api.autosync_status",
    "api.autosync_run",
    "api.list_exclusions",
    "api.add_exclusion",
    "api.delete_exclusion",
    "api.exclusion_state",
    "api.set_exclusion_state",
}


def register_blueprints(app):
    app.register_blueprint(pages.bp)

    api = Blueprint("api", __name__, url_prefix="/api")
    for module in (api_media, api_queue, api_settings, api_library, api_autosync):
        module.register(api)
    app.register_blueprint(api)
