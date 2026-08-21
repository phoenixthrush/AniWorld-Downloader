"""Reading and writing the web UI settings.

Settings live in environment variables. Most are session-only: they apply to the
running process and reset on restart unless the user puts them in their .env.
The Discord bot keys are the exception, a token that vanished on restart would
be useless, so those are written through to the .env file.
"""

import os

import niquests as requests

from ..config import (
    ANIWORLD_CONFIG_DIR,
    LANG_LABELS,
    get_provider_fallback_order,
    parse_provider_order,
)
from ..logger import get_logger
from . import paths, schedule
from .media import WORKING_PROVIDERS

logger = get_logger(__name__)

UI_LANGUAGES = ("en", "de")
OUTPUT_FORMATS = ("mkv", "mp4")

# How Auto-Sync decides when to run: every so often, or at fixed times
AUTOSYNC_MODES = ("interval", "cron")
DEFAULT_AUTOSYNC_INTERVAL_SECONDS = 24 * 60 * 60
DEFAULT_AUTOSYNC_CRON = "0 3 * * *"

DISCORD_MODES = ("standard", "advanced")
DISCORD_LANGUAGES = ("en", "de")

# Sent instead of the real token so it never leaves the server.
SECRET_PLACEHOLDER = "•" * 8

DISCORD_KEYS = {
    "enabled": "ANIWORLD_DISCORD_BOT_ENABLED",
    "token": "ANIWORLD_DISCORD_TOKEN",
    "owner_id": "ANIWORLD_DISCORD_OWNER_ID",
    "mode": "ANIWORLD_DISCORD_MODE",
    "request_role_id": "ANIWORLD_DISCORD_REQUEST_ROLE_ID",
    "guild_id": "ANIWORLD_DISCORD_GUILD_ID",
    "language": "ANIWORLD_DISCORD_LANGUAGE",
    "announce_channel_id": "ANIWORLD_DISCORD_ANNOUNCE_CHANNEL_ID",
}

_IP_LOOKUP_URLS = (
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/all.json",
)


class SettingsError(ValueError):
    """Raised for an invalid settings payload."""


def _flag(key, default="0"):
    return os.environ.get(key, default) == "1"


def ui_language():
    lang = os.environ.get("ANIWORLD_UI_LANGUAGE", "en").lower()
    return lang if lang in UI_LANGUAGES else "en"


def library_enabled():
    return _flag("ANIWORLD_ENABLE_LIBRARY", "1")


def autosync_enabled():
    return _flag("ANIWORLD_ENABLE_AUTOSYNC")


def autosync_new_only():
    """Queue only the episodes from the feed instead of filling the gaps.

    Off by default so upgrading does not silently change what AutoSync does.
    """
    return _flag("ANIWORLD_AUTOSYNC_NEW_ONLY")


# ---------------------------------------------------------------------------
# When Auto-Sync runs
#
# A broken value in the environment must never take the worker down with it, so
# every reader below falls back to the default and says so in the log. The
# settings page rejects bad input up front, this is for a hand-edited .env.
# ---------------------------------------------------------------------------
def autosync_mode():
    mode = os.environ.get("ANIWORLD_AUTOSYNC_MODE", "").strip().lower()
    return mode if mode in AUTOSYNC_MODES else "interval"


def autosync_interval_seconds():
    """Seconds between two runs in interval mode."""
    raw = os.environ.get("ANIWORLD_AUTOSYNC_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_AUTOSYNC_INTERVAL_SECONDS
    try:
        return schedule.parse_interval(raw)
    except schedule.ScheduleError as exc:
        logger.warning("Ignoring ANIWORLD_AUTOSYNC_INTERVAL=%r: %s", raw, exc)
        return DEFAULT_AUTOSYNC_INTERVAL_SECONDS


def autosync_interval():
    """The same interval written the way it is stored, e.g. "24h"."""
    return schedule.format_interval(autosync_interval_seconds())


def autosync_cron():
    """The cron expression for fixed times, normalised."""
    raw = os.environ.get("ANIWORLD_AUTOSYNC_CRON", "").strip()
    if not raw:
        return DEFAULT_AUTOSYNC_CRON
    try:
        return schedule.parse(raw).expression
    except schedule.ScheduleError as exc:
        logger.warning("Ignoring ANIWORLD_AUTOSYNC_CRON=%r: %s", raw, exc)
        return DEFAULT_AUTOSYNC_CRON


def autosync_cron_schedule():
    """Parsed fixed times, or None when Auto-Sync runs on an interval."""
    if autosync_mode() != "cron":
        return None
    return schedule.parse(autosync_cron())


def autosync_schedule_description(language=None):
    """One line for the UI: "Every day at 22:00", "Every 6 hours"."""
    language = language or ui_language()
    fixed = autosync_cron_schedule()
    if fixed is not None:
        return fixed.describe(language)
    return schedule.describe_interval(autosync_interval_seconds(), language)


def htv_enabled():
    return _flag("ANIWORLD_ENABLE_HTV")


def burningseries_enabled():
    """Off by default: the site is geo-blocked and behind Google reCAPTCHA."""
    return _flag("ANIWORLD_ENABLE_BURNINGSERIES")


def kinox_enabled():
    """Off by default: every download needs a captcha solved by hand."""
    return _flag("ANIWORLD_ENABLE_KINOX")


def english_sub_disabled():
    return _flag("ANIWORLD_DISABLE_ENGLISH_SUB")


def default_language():
    language = os.environ.get("ANIWORLD_LANGUAGE", "German Dub")
    return language if language in LANG_LABELS.values() else "German Dub"


# ---------------------------------------------------------------------------
# Naming template (drives the output container)
# ---------------------------------------------------------------------------
def _naming_template():
    from ..config import NAMING_TEMPLATE

    return os.environ.get("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)


def output_format():
    """Container implied by the naming template's file extension."""
    last = _naming_template().rstrip('"').split("/")[-1]
    if "." in last:
        extension = last.rsplit(".", 1)[1].strip().strip('"').lower()
        if extension:
            return extension
    return "mkv"


def _template_with_extension(extension):
    template = _naming_template()
    quoted = template.startswith('"') and template.endswith('"')
    if quoted:
        template = template[1:-1]
    parts = template.split("/")
    parts[-1] = parts[-1].rsplit(".", 1)[0] + f".{extension}"
    rebuilt = "/".join(parts)
    return f'"{rebuilt}"' if quoted else rebuilt


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
def discord_settings():
    return {
        "enabled": _flag(DISCORD_KEYS["enabled"]),
        "token_set": bool(os.environ.get(DISCORD_KEYS["token"], "").strip()),
        "owner_id": os.environ.get(DISCORD_KEYS["owner_id"], ""),
        "mode": os.environ.get(DISCORD_KEYS["mode"], "standard"),
        "request_role_id": os.environ.get(DISCORD_KEYS["request_role_id"], ""),
        "guild_id": os.environ.get(DISCORD_KEYS["guild_id"], ""),
        "language": os.environ.get(DISCORD_KEYS["language"], "en"),
        "announce_channel_id": os.environ.get(DISCORD_KEYS["announce_channel_id"], ""),
    }


def _collect_discord(payload, updates):
    if not isinstance(payload, dict):
        raise SettingsError("discord must be an object")

    if "enabled" in payload:
        updates[DISCORD_KEYS["enabled"]] = "1" if payload["enabled"] else "0"

    if "token" in payload:
        token = str(payload["token"]).strip()
        # The UI echoes the placeholder back when the field was left alone
        if token != SECRET_PLACEHOLDER:
            updates[DISCORD_KEYS["token"]] = token

    if "mode" in payload:
        mode = str(payload["mode"]).strip().lower()
        if mode not in DISCORD_MODES:
            raise SettingsError(f"Invalid discord mode: {mode}")
        updates[DISCORD_KEYS["mode"]] = mode

    if "language" in payload:
        language = str(payload["language"]).strip().lower()
        if language not in DISCORD_LANGUAGES:
            raise SettingsError(f"Invalid discord language: {language}")
        updates[DISCORD_KEYS["language"]] = language

    for field in ("owner_id", "request_role_id", "guild_id", "announce_channel_id"):
        if field in payload:
            value = str(payload[field]).strip()
            if value and not value.isdigit():
                raise SettingsError(f"Invalid discord {field}: must be a numeric ID")
            updates[DISCORD_KEYS[field]] = value


def _persist_discord(updates):
    subset = {k: v for k, v in updates.items() if k in set(DISCORD_KEYS.values())}
    if not subset:
        return
    try:
        from ..env import persist_env_values

        persist_env_values(ANIWORLD_CONFIG_DIR / ".env", subset)
    except OSError as exc:
        logger.warning("Could not persist Discord settings to .env: %s", exc)


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------
def read_settings():
    return {
        "download_path": str(paths.default_download_path()),
        "lang_separation": paths.lang_separation_enabled(),
        "disable_english_sub": english_sub_disabled(),
        "enable_htv": htv_enabled(),
        "enable_burningseries": burningseries_enabled(),
        "enable_kinox": kinox_enabled(),
        "enable_library": library_enabled(),
        "enable_autosync": autosync_enabled(),
        "autosync_new_only": autosync_new_only(),
        "autosync_mode": autosync_mode(),
        "autosync_interval": autosync_interval(),
        "autosync_interval_seconds": autosync_interval_seconds(),
        "autosync_cron": autosync_cron(),
        "autosync_schedule": autosync_schedule_description(),
        "movie_folder": _flag("ANIWORLD_MOVIE_FOLDER", "1"),
        "ui_language": ui_language(),
        "output_format": output_format(),
        "provider_fallback_order": list(get_provider_fallback_order(WORKING_PROVIDERS)),
        "available_providers": list(WORKING_PROVIDERS),
        "available_ui_languages": list(UI_LANGUAGES),
        "available_output_formats": list(OUTPUT_FORMATS),
        "available_autosync_modes": list(AUTOSYNC_MODES),
        "discord": discord_settings(),
    }


_BOOL_SETTINGS = {
    "lang_separation": "ANIWORLD_LANG_SEPARATION",
    "disable_english_sub": "ANIWORLD_DISABLE_ENGLISH_SUB",
    "enable_htv": "ANIWORLD_ENABLE_HTV",
    "enable_burningseries": "ANIWORLD_ENABLE_BURNINGSERIES",
    "enable_kinox": "ANIWORLD_ENABLE_KINOX",
    "enable_library": "ANIWORLD_ENABLE_LIBRARY",
    "enable_autosync": "ANIWORLD_ENABLE_AUTOSYNC",
    "autosync_new_only": "ANIWORLD_AUTOSYNC_NEW_ONLY",
    "movie_folder": "ANIWORLD_MOVIE_FOLDER",
}


def _collect_provider_order(raw, updates):
    if isinstance(raw, (list, tuple)):
        requested = [str(item).strip() for item in raw]
    else:
        requested = [item.strip() for item in str(raw).split(",")]
    requested = [item for item in requested if item]

    if not requested:
        raise SettingsError("provider_fallback_order cannot be empty")
    unknown = sorted({p for p in requested if p not in WORKING_PROVIDERS})
    if unknown:
        raise SettingsError(
            "Invalid provider_fallback_order entries: " + ", ".join(unknown)
        )
    if len(set(requested)) != len(requested):
        raise SettingsError("provider_fallback_order contains duplicates")

    updates["ANIWORLD_PROVIDER_FALLBACK_ORDER"] = ",".join(
        parse_provider_order(",".join(requested), allowed_providers=WORKING_PROVIDERS)
    )


def _collect_autosync_schedule(data, updates):
    """Validate the Auto-Sync schedule fields, both stored the way they parse."""
    if "autosync_mode" in data:
        mode = str(data["autosync_mode"]).strip().lower()
        if mode not in AUTOSYNC_MODES:
            raise SettingsError(f"Invalid autosync_mode: {mode}")
        updates["ANIWORLD_AUTOSYNC_MODE"] = mode

    if "autosync_interval" in data:
        try:
            seconds = schedule.parse_interval(data["autosync_interval"])
        except schedule.ScheduleError as exc:
            raise SettingsError(str(exc)) from None
        updates["ANIWORLD_AUTOSYNC_INTERVAL"] = schedule.format_interval(seconds)

    if "autosync_cron" in data:
        # Plain language is accepted here and comes back out as cron
        try:
            parsed = schedule.parse(str(data["autosync_cron"]))
        except schedule.ScheduleError as exc:
            raise SettingsError(str(exc)) from None
        updates["ANIWORLD_AUTOSYNC_CRON"] = parsed.expression


def update_settings(data):
    """Apply a settings payload. Raises SettingsError on invalid input.

    Returns True when the Discord config changed, so the caller can restart the bot.
    """
    updates = {}

    if "download_path" in data:
        updates["ANIWORLD_DOWNLOAD_PATH"] = str(data["download_path"]).strip()

    for field, key in _BOOL_SETTINGS.items():
        if field in data:
            updates[key] = "1" if data[field] else "0"

    if "ui_language" in data:
        language = str(data["ui_language"]).strip().lower()
        if language not in UI_LANGUAGES:
            raise SettingsError(f"Invalid ui_language: {language}")
        updates["ANIWORLD_UI_LANGUAGE"] = language

    if "output_format" in data:
        fmt = str(data["output_format"]).strip().lower().lstrip(".")
        if fmt not in OUTPUT_FORMATS:
            raise SettingsError(f"Invalid output_format: {fmt}")
        updates["ANIWORLD_NAMING_TEMPLATE"] = _template_with_extension(fmt)

    if "provider_fallback_order" in data:
        _collect_provider_order(data["provider_fallback_order"], updates)

    _collect_autosync_schedule(data, updates)

    discord_changed = "discord" in data
    if discord_changed:
        _collect_discord(data["discord"], updates)

    for key, value in updates.items():
        os.environ[key] = value

    if discord_changed:
        _persist_discord(updates)

    return discord_changed


# ---------------------------------------------------------------------------
# Public IP lookup (only run when the user presses reveal)
# ---------------------------------------------------------------------------
def fetch_public_ip():
    last_error = None
    for url in _IP_LOOKUP_URLS:
        try:
            response = requests.get(
                url, headers={"User-Agent": "AniWorld Downloader"}, timeout=5
            )
            response.raise_for_status()
            payload = response.json()
            ip = (payload.get("ip") or payload.get("ip_addr") or "").strip()
            if ip:
                return {"ip": ip, "source": url}
            last_error = "No IP address returned by upstream service"
        except requests.RequestException as exc:
            last_error = str(exc)
        except ValueError as exc:
            last_error = f"Invalid response: {exc}"
    raise RuntimeError(last_error or "Failed to resolve public IP")
