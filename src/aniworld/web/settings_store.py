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
from .media import SITE_KEYS, SITE_LABELS, SITES_OFF_BY_DEFAULT, WORKING_PROVIDERS

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


# ---------------------------------------------------------------------------
# Sites
#
# Every site can be switched off, which takes its tab off the home page along
# with the rows it fills there. Three of them start off (see media.py), the
# rest start on, and all of them follow the same ANIWORLD_ENABLE_<SITE> name.
# ---------------------------------------------------------------------------
def site_env_key(site):
    return f"ANIWORLD_ENABLE_{site.upper()}"


def site_enabled(site):
    if site not in SITE_KEYS:
        return False
    return _flag(site_env_key(site), "0" if site in SITES_OFF_BY_DEFAULT else "1")


def enabled_sites():
    """{site key: on or off} for every site there is."""
    return {site: site_enabled(site) for site in SITE_KEYS}


def htv_enabled():
    return site_enabled("htv")


def burningseries_enabled():
    """Off by default: the site is geo-blocked and behind Google reCAPTCHA."""
    return site_enabled("burningseries")


def kinox_enabled():
    """Off by default: every download needs a captcha solved by hand."""
    return site_enabled("kinox")


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
# Where a download lands
#
# Not a second implementation of the naming rules: the episode path is built by
# the downloader itself, a real AniworldEpisode handed a stand-in series, so the
# box on the settings page cannot say one thing while the disk gets another.
#
# The stand-in carries what a real page gives, which is why the title is the
# whole cleaned title and the year is a range rather than one year.
#
# Movies never go through the naming template. Every movie site writes
# "Title (Year)", inside a folder of the same name unless that is switched off,
# and takes only the file extension from the template.
# ---------------------------------------------------------------------------
_PREVIEW_URL = (
    "https://aniworld.to/anime/stream/konosuba-gods-blessing-on-this-wonderful-world"
    "/staffel-1/episode-3"
)
_PREVIEW_TITLE = "KonoSuba God\u2019s blessing on this wonderful world!"
_PREVIEW_YEARS = "2016-2025"
_PREVIEW_IMDB = "tt5370118"
_PREVIEW_RESOLUTION = "1080p"
_PREVIEW_MOVIE = ("Your Name", "2016")


def _preview_episode(root, language):
    """A real episode object, built without touching the network."""
    from types import SimpleNamespace

    from ..models.aniworld_to.episode import AniworldEpisode

    episode = AniworldEpisode(
        url=_PREVIEW_URL,
        series=SimpleNamespace(
            title_cleaned=_PREVIEW_TITLE,
            release_year=_PREVIEW_YEARS,
            imdb=_PREVIEW_IMDB,
        ),
        season=SimpleNamespace(season_number=1),
        episode_number=3,
        selected_path=str(root),
        selected_language=language,
    )
    # What the downloader sets once it has probed the finished file, so a
    # template using {resolution} previews the name the file ends up with
    episode._resolution = _PREVIEW_RESOLUTION
    return episode


def preview_paths(download_path=None):
    """The full path a movie and an episode would be written to."""
    from ..models.common.common import movie_folder_enabled

    root = (
        paths.expand(download_path) if download_path else paths.default_download_path()
    )
    language = default_language()
    if paths.lang_separation_enabled():
        root = root / paths.lang_folder_for(language)

    try:
        episode = _preview_episode(root, language)
        episode_path = str(episode._episode_path)
        extension = episode._file_extension
    except KeyError as exc:
        # The downloader raises the same way on the first download, so saying
        # it here is the whole point of having a preview
        return {
            "error": f"The naming template uses {{{exc.args[0]}}}, "
            "which is not one of the placeholders a download can fill in"
        }
    except Exception as exc:
        # A preview must never take the settings page down with it
        logger.warning("Could not work out the download path preview: %s", exc)
        return {"error": "Could not work this out from the naming template"}

    title, year = _PREVIEW_MOVIE
    movie_name = f"{title} ({year})"
    folder = root / movie_name if movie_folder_enabled() else root
    return {
        "episode": episode_path,
        "movie": str(folder / f"{movie_name}.{extension}"),
    }


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
        **{f"enable_{site}": state for site, state in enabled_sites().items()},
        "enable_library": library_enabled(),
        "enable_autosync": autosync_enabled(),
        "autosync_new_only": autosync_new_only(),
        "autosync_mode": autosync_mode(),
        "autosync_interval": autosync_interval(),
        "autosync_interval_seconds": autosync_interval_seconds(),
        "autosync_cron": autosync_cron(),
        "autosync_schedule": autosync_schedule_description(),
        "path_preview": preview_paths(),
        "movie_folder": _flag("ANIWORLD_MOVIE_FOLDER", "1"),
        "ui_language": ui_language(),
        "output_format": output_format(),
        "provider_fallback_order": list(get_provider_fallback_order(WORKING_PROVIDERS)),
        "available_providers": list(WORKING_PROVIDERS),
        "available_ui_languages": list(UI_LANGUAGES),
        "available_output_formats": list(OUTPUT_FORMATS),
        "available_autosync_modes": list(AUTOSYNC_MODES),
        "available_sites": [
            {
                "key": site,
                "label": SITE_LABELS[site],
                "default_on": site not in SITES_OFF_BY_DEFAULT,
            }
            for site in SITE_KEYS
        ],
        "discord": discord_settings(),
    }


_BOOL_SETTINGS = {
    "lang_separation": "ANIWORLD_LANG_SEPARATION",
    "disable_english_sub": "ANIWORLD_DISABLE_ENGLISH_SUB",
    "enable_library": "ANIWORLD_ENABLE_LIBRARY",
    "enable_autosync": "ANIWORLD_ENABLE_AUTOSYNC",
    "autosync_new_only": "ANIWORLD_AUTOSYNC_NEW_ONLY",
    "movie_folder": "ANIWORLD_MOVIE_FOLDER",
    **{f"enable_{site}": site_env_key(site) for site in SITE_KEYS},
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


def _check_a_site_is_left(data):
    """Refuse the change that would leave the home page with nothing on it.

    Only a payload that touches a site is checked: a .env with everything off
    is the user's business, and must not block every other setting on the page.
    """
    if not any(f"enable_{site}" in data for site in SITE_KEYS):
        return

    wanted = {
        site: bool(data[f"enable_{site}"])
        if f"enable_{site}" in data
        else site_enabled(site)
        for site in SITE_KEYS
    }
    if not any(wanted.values()):
        raise SettingsError("At least one site has to stay enabled")


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
    _check_a_site_is_left(data)

    discord_changed = "discord" in data
    if discord_changed:
        _collect_discord(data["discord"], updates)

    for key, value in updates.items():
        os.environ[key] = value

    if discord_changed:
        _persist_discord(updates)

    return discord_changed


# ---------------------------------------------------------------------------
# Exporting what is running
#
# Most settings live in the environment and go back to their defaults on a
# restart, which is deliberate. This writes out what the instance is using
# right now as a .env, so anyone who wants a setting to stick can save it.
#
# Secrets are left out on purpose. The Discord token is already written to the
# .env by the bot settings themselves, and nothing else here should end up in
# a file that lands in a downloads folder.
# ---------------------------------------------------------------------------
def _env_sections():
    """(heading, [(key, value)]) in the order they should be written."""
    discord = discord_settings()
    return [
        (
            "General",
            [
                ("ANIWORLD_DOWNLOAD_PATH", str(paths.default_download_path())),
                ("ANIWORLD_UI_LANGUAGE", ui_language()),
            ],
        ),
        (
            "Downloads",
            [
                ("ANIWORLD_NAMING_TEMPLATE", _naming_template()),
                (
                    "ANIWORLD_PROVIDER_FALLBACK_ORDER",
                    ",".join(get_provider_fallback_order(WORKING_PROVIDERS)),
                ),
                ("ANIWORLD_LANG_SEPARATION", _one_or_zero(paths.lang_separation_enabled())),
                ("ANIWORLD_DISABLE_ENGLISH_SUB", _one_or_zero(english_sub_disabled())),
                ("ANIWORLD_MOVIE_FOLDER", _one_or_zero(_flag("ANIWORLD_MOVIE_FOLDER", "1"))),
            ],
        ),
        (
            "Sites",
            [
                (site_env_key(site), _one_or_zero(state))
                for site, state in enabled_sites().items()
            ],
        ),
        (
            "Library and Auto-Sync",
            [
                ("ANIWORLD_ENABLE_LIBRARY", _one_or_zero(library_enabled())),
                ("ANIWORLD_ENABLE_AUTOSYNC", _one_or_zero(autosync_enabled())),
                ("ANIWORLD_AUTOSYNC_NEW_ONLY", _one_or_zero(autosync_new_only())),
                ("ANIWORLD_AUTOSYNC_MODE", autosync_mode()),
                ("ANIWORLD_AUTOSYNC_INTERVAL", autosync_interval()),
                ("ANIWORLD_AUTOSYNC_CRON", autosync_cron()),
            ],
        ),
        (
            "Discord bot (the token is not exported, it is already in your .env)",
            [
                (DISCORD_KEYS["enabled"], _one_or_zero(discord["enabled"])),
                (DISCORD_KEYS["owner_id"], discord["owner_id"]),
                (DISCORD_KEYS["mode"], discord["mode"]),
                (DISCORD_KEYS["language"], discord["language"]),
                (DISCORD_KEYS["request_role_id"], discord["request_role_id"]),
                (DISCORD_KEYS["guild_id"], discord["guild_id"]),
                (DISCORD_KEYS["announce_channel_id"], discord["announce_channel_id"]),
            ],
        ),
    ]


def _one_or_zero(state):
    return "1" if state else "0"


def _env_value(value):
    """Quote the way the shipped .env.example does, only where it is needed."""
    value = "" if value is None else str(value)
    if value and value[0] in "\"'" and value[-1] == value[0]:
        return value
    return f'"{value}"' if any(ch in value for ch in ' \t#') else value


def export_env():
    """The running settings as the text of a .env file."""
    lines = [
        "# AniWorld Downloader settings, exported from the web UI.",
        "#",
        "# These are the values this instance is running with right now. Save the",
        "# file as your .env, or copy the lines you want into the one you have, and",
        "# they will be there again after a restart.",
        "#",
        "# Passwords and tokens are deliberately not in here: the Discord bot token,",
        "# the OIDC client secret and any admin password stay where they are.",
    ]
    for heading, entries in _env_sections():
        lines.append("")
        lines.append(f"# ===== {heading} =====")
        lines.extend(f"{key}={_env_value(value)}" for key, value in entries)
    return "\n".join(lines) + "\n"


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
