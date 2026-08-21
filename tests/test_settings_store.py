"""Reading and writing settings, including every validation rule."""

import os

import pytest

from aniworld.web import settings_store
from aniworld.web.media import WORKING_PROVIDERS
from aniworld.web.settings_store import SettingsError, update_settings


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
def test_defaults_of_a_fresh_install():
    settings = settings_store.read_settings()
    assert settings["ui_language"] == "en"
    assert settings["lang_separation"] is False
    assert settings["disable_english_sub"] is False
    assert settings["enable_htv"] is False
    assert settings["enable_burningseries"] is False
    assert settings["enable_kinox"] is False
    assert settings["enable_library"] is True, "the library is on unless turned off"
    assert settings["enable_autosync"] is False
    assert settings["movie_folder"] is True
    assert settings["output_format"] == "mkv"


def test_read_settings_lists_the_choices():
    settings = settings_store.read_settings()
    assert settings["available_ui_languages"] == ["en", "de"]
    assert settings["available_output_formats"] == ["mkv", "mp4"]
    assert settings["available_providers"] == list(WORKING_PROVIDERS)


def test_read_settings_never_leaks_the_discord_token(monkeypatch):
    monkeypatch.setenv("ANIWORLD_DISCORD_TOKEN", "super-secret-token")
    discord = settings_store.read_settings()["discord"]
    assert discord["token_set"] is True
    assert "token" not in discord
    assert "super-secret-token" not in str(discord)


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "field,env_key",
    [
        ("lang_separation", "ANIWORLD_LANG_SEPARATION"),
        ("disable_english_sub", "ANIWORLD_DISABLE_ENGLISH_SUB"),
        ("enable_htv", "ANIWORLD_ENABLE_HTV"),
        ("enable_burningseries", "ANIWORLD_ENABLE_BURNINGSERIES"),
        ("enable_kinox", "ANIWORLD_ENABLE_KINOX"),
        ("enable_library", "ANIWORLD_ENABLE_LIBRARY"),
        ("enable_autosync", "ANIWORLD_ENABLE_AUTOSYNC"),
        ("movie_folder", "ANIWORLD_MOVIE_FOLDER"),
    ],
)
def test_every_toggle_round_trips(field, env_key):
    update_settings({field: True})
    assert os.environ[env_key] == "1"
    assert settings_store.read_settings()[field] is True

    update_settings({field: False})
    assert os.environ[env_key] == "0"
    assert settings_store.read_settings()[field] is False


# ---------------------------------------------------------------------------
# The Auto-Sync schedule
#
# Whatever comes in is stored the way it parses, so the settings page always
# gets a clean value back no matter how it was written.
# ---------------------------------------------------------------------------
def test_auto_sync_runs_once_a_day_unless_told_otherwise():
    settings = settings_store.read_settings()
    assert settings["autosync_mode"] == "interval"
    assert settings["autosync_interval"] == "24h"
    assert settings["autosync_interval_seconds"] == 86400
    assert settings["autosync_cron"] == "0 3 * * *"
    assert settings["autosync_schedule"] == "Every day"


def test_the_mode_can_be_switched():
    update_settings({"autosync_mode": "cron"})
    assert os.environ["ANIWORLD_AUTOSYNC_MODE"] == "cron"
    assert settings_store.read_settings()["autosync_mode"] == "cron"


def test_an_unknown_mode_is_rejected():
    with pytest.raises(SettingsError, match="weekly"):
        update_settings({"autosync_mode": "weekly"})


@pytest.mark.parametrize(
    "written,stored", [("6h", "6h"), ("90m", "90m"), (12, "12h"), ("1h30m", "90m")]
)
def test_an_interval_is_stored_the_way_it_parses(written, stored):
    update_settings({"autosync_interval": written})
    assert os.environ["ANIWORLD_AUTOSYNC_INTERVAL"] == stored
    assert settings_store.read_settings()["autosync_interval"] == stored


def test_an_impossible_interval_is_rejected():
    with pytest.raises(SettingsError, match="at least"):
        update_settings({"autosync_interval": "10s"})


def test_a_nonsense_interval_is_rejected():
    with pytest.raises(SettingsError):
        update_settings({"autosync_interval": "sometimes"})


def test_fixed_times_can_be_written_as_cron():
    update_settings({"autosync_cron": "0 22 * * 1,5"})
    assert os.environ["ANIWORLD_AUTOSYNC_CRON"] == "0 22 * * 1,5"


def test_fixed_times_can_be_written_as_a_sentence():
    update_settings({"autosync_cron": "every monday and friday at 10pm"})
    assert os.environ["ANIWORLD_AUTOSYNC_CRON"] == "0 22 * * 1,5"


def test_a_nonsense_schedule_is_rejected():
    with pytest.raises(SettingsError, match="blursday"):
        update_settings({"autosync_cron": "every blursday"})


def test_a_rejected_schedule_leaves_the_old_one():
    update_settings({"autosync_cron": "0 22 * * 1"})
    with pytest.raises(SettingsError):
        update_settings({"autosync_cron": "0 99 * * *"})
    assert settings_store.autosync_cron() == "0 22 * * 1"


def test_the_schedule_is_described_for_the_page(monkeypatch):
    monkeypatch.setenv("ANIWORLD_AUTOSYNC_MODE", "cron")
    update_settings({"autosync_cron": "every day at 08:00, 22:30"})
    assert settings_store.autosync_schedule_description() == (
        "Every day at 08:00 and 22:30"
    )


def test_the_description_follows_the_ui_language(monkeypatch):
    monkeypatch.setenv("ANIWORLD_UI_LANGUAGE", "de")
    assert settings_store.autosync_schedule_description() == "Jeden Tag"


@pytest.mark.parametrize(
    "key,value",
    [
        ("ANIWORLD_AUTOSYNC_MODE", "yearly"),
        ("ANIWORLD_AUTOSYNC_INTERVAL", "whenever"),
        ("ANIWORLD_AUTOSYNC_CRON", "0 99 * * *"),
    ],
)
def test_a_hand_edited_env_never_breaks_the_worker(monkeypatch, key, value):
    """The settings page validates, a text editor does not."""
    monkeypatch.setenv(key, value)
    settings = settings_store.read_settings()
    assert settings["autosync_mode"] in settings_store.AUTOSYNC_MODES
    assert settings["autosync_interval"] == "24h"
    assert settings["autosync_cron"] == "0 3 * * *"


@pytest.mark.parametrize("truthy", [True, 1, "yes", "0", [1]])
def test_anything_truthy_turns_a_toggle_on(truthy):
    update_settings({"enable_htv": truthy})
    assert settings_store.htv_enabled() is True


@pytest.mark.parametrize("falsy", [False, 0, "", None, []])
def test_anything_falsy_turns_a_toggle_off(falsy):
    update_settings({"enable_htv": True})
    update_settings({"enable_htv": falsy})
    assert settings_store.htv_enabled() is False


def test_untouched_settings_are_left_alone():
    update_settings({"enable_htv": True, "lang_separation": True})
    update_settings({"enable_htv": False})
    assert settings_store.read_settings()["lang_separation"] is True


# ---------------------------------------------------------------------------
# UI language
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("language", ["en", "de", "DE", " de "])
def test_supported_ui_languages_are_accepted(language):
    update_settings({"ui_language": language})
    assert settings_store.ui_language() == language.strip().lower()


@pytest.mark.parametrize("language", ["fr", "klingon", ""])
def test_unsupported_ui_languages_are_refused(language):
    with pytest.raises(SettingsError):
        update_settings({"ui_language": language})


def test_a_junk_language_in_the_environment_falls_back(monkeypatch):
    monkeypatch.setenv("ANIWORLD_UI_LANGUAGE", "klingon")
    assert settings_store.ui_language() == "en"


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["mkv", "mp4", "MP4", ".mp4", " mp4 "])
def test_supported_formats_are_accepted(fmt):
    update_settings({"output_format": fmt})
    assert settings_store.output_format() == fmt.strip().lower().lstrip(".")


@pytest.mark.parametrize("fmt", ["avi", "exe", ""])
def test_unsupported_formats_are_refused(fmt):
    with pytest.raises(SettingsError):
        update_settings({"output_format": fmt})


def test_changing_the_format_only_touches_the_extension():
    update_settings({"output_format": "mp4"})
    template = os.environ["ANIWORLD_NAMING_TEMPLATE"]
    assert template.endswith(".mp4")
    assert "{title}" in template and "Season {season}" in template


def test_the_format_survives_a_round_trip():
    update_settings({"output_format": "mp4"})
    update_settings({"output_format": "mkv"})
    assert settings_store.output_format() == "mkv"
    assert os.environ["ANIWORLD_NAMING_TEMPLATE"].endswith(".mkv")


def test_a_quoted_template_stays_quoted(monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", '"{title}/{title} S{season}E{episode}.mkv"'
    )
    update_settings({"output_format": "mp4"})
    template = os.environ["ANIWORLD_NAMING_TEMPLATE"]
    assert template.startswith('"') and template.endswith('"')
    assert settings_store.output_format() == "mp4"


def test_a_template_without_an_extension_reads_as_mkv(monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "{title}/{title} S{season}E{episode}"
    )
    assert settings_store.output_format() == "mkv"


def test_a_dot_in_the_folder_does_not_confuse_the_format(monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "{title} (2024)/Season 1/{title} S01E01.mp4"
    )
    assert settings_store.output_format() == "mp4"


# ---------------------------------------------------------------------------
# Provider fallback order
# ---------------------------------------------------------------------------
def test_the_order_can_be_rearranged():
    reversed_order = list(reversed(WORKING_PROVIDERS))
    update_settings({"provider_fallback_order": reversed_order})
    assert settings_store.read_settings()["provider_fallback_order"] == reversed_order


def test_a_partial_order_keeps_the_rest_behind_it():
    update_settings({"provider_fallback_order": [WORKING_PROVIDERS[-1]]})
    order = settings_store.read_settings()["provider_fallback_order"]
    assert order[0] == WORKING_PROVIDERS[-1]
    assert sorted(order) == sorted(WORKING_PROVIDERS), "no provider may be dropped"


def test_a_comma_separated_string_works_too():
    update_settings({"provider_fallback_order": ",".join(reversed(WORKING_PROVIDERS))})
    assert (
        settings_store.read_settings()["provider_fallback_order"][0]
        == (WORKING_PROVIDERS[-1])
    )


def test_whitespace_around_names_is_ignored():
    update_settings({"provider_fallback_order": [f"  {WORKING_PROVIDERS[1]}  "]})
    assert (
        settings_store.read_settings()["provider_fallback_order"][0]
        == (WORKING_PROVIDERS[1])
    )


def test_an_unknown_provider_is_refused():
    with pytest.raises(SettingsError) as exc:
        update_settings({"provider_fallback_order": ["VOE", "TotallyRealHoster"]})
    assert "TotallyRealHoster" in str(exc.value)


def test_duplicates_are_refused():
    with pytest.raises(SettingsError) as exc:
        update_settings({"provider_fallback_order": ["VOE", "VOE"]})
    assert "duplicates" in str(exc.value)


@pytest.mark.parametrize("empty", [[], "", "  ", [" "]])
def test_an_empty_order_is_refused(empty):
    with pytest.raises(SettingsError):
        update_settings({"provider_fallback_order": empty})


def test_a_rejected_order_changes_nothing():
    update_settings({"provider_fallback_order": list(reversed(WORKING_PROVIDERS))})
    before = settings_store.read_settings()["provider_fallback_order"]
    with pytest.raises(SettingsError):
        update_settings({"provider_fallback_order": ["Nope"]})
    assert settings_store.read_settings()["provider_fallback_order"] == before


def test_a_rejected_field_does_not_apply_the_valid_ones():
    """update_settings validates everything before writing anything."""
    with pytest.raises(SettingsError):
        update_settings({"enable_htv": True, "ui_language": "klingon"})
    assert settings_store.htv_enabled() is False


# ---------------------------------------------------------------------------
# Download path
# ---------------------------------------------------------------------------
def test_the_download_path_can_be_changed(tmp_path):
    update_settings({"download_path": str(tmp_path / "media")})
    assert settings_store.read_settings()["download_path"] == str(tmp_path / "media")


def test_the_download_path_is_trimmed(tmp_path):
    update_settings({"download_path": f"  {tmp_path}  "})
    assert settings_store.read_settings()["download_path"] == str(tmp_path)


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
def test_discord_settings_round_trip():
    changed = update_settings(
        {
            "discord": {
                "enabled": True,
                "token": "a-token",
                "owner_id": "123",
                "mode": "advanced",
                "language": "de",
                "guild_id": "456",
            }
        }
    )
    assert changed is True
    discord = settings_store.discord_settings()
    assert discord["enabled"] is True
    assert discord["token_set"] is True
    assert discord["owner_id"] == "123"
    assert discord["mode"] == "advanced"
    assert discord["language"] == "de"


def test_other_settings_do_not_report_a_discord_change():
    assert update_settings({"enable_htv": True}) is False


def test_the_placeholder_does_not_overwrite_the_token():
    update_settings({"discord": {"token": "real-token"}})
    update_settings({"discord": {"token": settings_store.SECRET_PLACEHOLDER}})
    assert os.environ["ANIWORLD_DISCORD_TOKEN"] == "real-token"


def test_the_token_can_be_cleared():
    update_settings({"discord": {"token": "real-token"}})
    update_settings({"discord": {"token": ""}})
    assert settings_store.discord_settings()["token_set"] is False


@pytest.mark.parametrize(
    "field", ["owner_id", "request_role_id", "guild_id", "announce_channel_id"]
)
def test_discord_ids_must_be_numeric(field):
    with pytest.raises(SettingsError) as exc:
        update_settings({"discord": {field: "not-a-number"}})
    assert field in str(exc.value)


@pytest.mark.parametrize(
    "field", ["owner_id", "request_role_id", "guild_id", "announce_channel_id"]
)
def test_discord_ids_may_be_blank(field):
    update_settings({"discord": {field: ""}})
    assert settings_store.discord_settings()[field] == ""


def test_an_invalid_discord_mode_is_refused():
    with pytest.raises(SettingsError):
        update_settings({"discord": {"mode": "chaotic"}})


def test_an_invalid_discord_language_is_refused():
    with pytest.raises(SettingsError):
        update_settings({"discord": {"language": "klingon"}})


def test_discord_must_be_an_object():
    with pytest.raises(SettingsError):
        update_settings({"discord": "yes please"})


def test_discord_settings_are_written_to_the_env_file():
    """A token that vanished on restart would be useless."""
    from aniworld.config import ANIWORLD_CONFIG_DIR

    update_settings({"discord": {"token": "persisted-token", "enabled": True}})
    written = (ANIWORLD_CONFIG_DIR / ".env").read_text(encoding="utf-8")
    assert "persisted-token" in written


def test_other_settings_are_not_written_to_the_env_file():
    from aniworld.config import ANIWORLD_CONFIG_DIR

    update_settings({"enable_htv": True, "ui_language": "de"})
    written = (ANIWORLD_CONFIG_DIR / ".env").read_text(encoding="utf-8")
    assert "ANIWORLD_ENABLE_HTV=1" not in written


# ---------------------------------------------------------------------------
# Language defaults
# ---------------------------------------------------------------------------
def test_the_default_language_can_be_set(monkeypatch):
    monkeypatch.setenv("ANIWORLD_LANGUAGE", "German Sub")
    assert settings_store.default_language() == "German Sub"


def test_a_junk_default_language_falls_back(monkeypatch):
    monkeypatch.setenv("ANIWORLD_LANGUAGE", "Pig Latin")
    assert settings_store.default_language() == "German Dub"


def test_an_empty_payload_changes_nothing():
    before = settings_store.read_settings()
    assert update_settings({}) is False
    assert settings_store.read_settings() == before
