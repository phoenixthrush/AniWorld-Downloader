import curses
import curses.ascii
import json
import os
import sys
from enum import Enum
from pathlib import Path

import npyscreen

from .config import INVERSE_LANG_KEY_MAP, LANG_LABELS, VERSION, logger
from .providers import resolve_provider


def _extract_menu_languages(provider_name: str, provider_data: dict) -> list[str]:
    languages: list[str] = []

    if provider_name == "AniWorld":
        for key in provider_data.keys():
            site_key = INVERSE_LANG_KEY_MAP.get(key)
            if site_key is None:
                continue
            label = LANG_LABELS.get(site_key)
            if label and label not in languages:
                languages.append(label)
        return languages

    if provider_name == "SerienStream":
        # SerienStream provider_data keys are usually tuples of Enums like
        # (Audio.GERMAN, Subtitles.NONE) or (Audio.ENGLISH, Subtitles.NONE).
        for key in provider_data.keys():
            if not (isinstance(key, tuple) and len(key) == 2):
                continue
            audio = getattr(key[0], "value", str(key[0]))
            audio_lower = str(audio).lower()
            if audio_lower == "german":
                label = "German Dub"
            elif audio_lower == "english":
                label = "English Dub"
            else:
                continue

            if label not in languages:
                languages.append(label)
        return languages

    return languages


def _extract_menu_providers(provider_data: dict) -> list[str]:
    provider_names: set[str] = set()

    for providers_map in provider_data.values():
        if isinstance(providers_map, dict):
            provider_names.update(str(p) for p in providers_map.keys())

    return sorted(provider_names)


# ============================================================
# Patch: Fix for Python 3.14+ buffer overflow in npyscreen
# ============================================================
if sys.version_info >= (3, 14):
    import npyscreen.proto_fm_screen_area as _npyscreen_area

    def _patched_max_physical(self):
        try:
            return (curses.LINES - 1, curses.COLS - 1)
        except Exception:
            try:
                size = os.get_terminal_size()
            except OSError:
                size = os.terminal_size((80, 24))
            return (size.lines - 1, size.columns - 1)

    _npyscreen_area.ScreenArea._max_physical = _patched_max_physical


# ============================================================
# Theme
# ============================================================
class CustomTheme(npyscreen.ThemeManager):
    """Color reference: https://npyscreen.readthedocs.io/color.html"""

    default_colors = {
        "DEFAULT": "WHITE_BLACK",
        "FORMDEFAULT": "MAGENTA_BLACK",
        "NO_EDIT": "BLUE_BLACK",
        "STANDOUT": "CYAN_BLACK",
        "CURSOR": "WHITE_BLACK",
        "CURSOR_INVERSE": "BLACK_WHITE",
        "LABEL": "CYAN_BLACK",
        "LABELBOLD": "CYAN_BLACK",
        "CONTROL": "GREEN_BLACK",
        "IMPORTANT": "GREEN_BLACK",
        "SAFE": "GREEN_BLACK",
        "WARNING": "YELLOW_BLACK",
        "DANGER": "RED_BLACK",
        "CRITICAL": "BLACK_RED",
        "GOOD": "GREEN_BLACK",
        "GOODHL": "GREEN_BLACK",
        "VERYGOOD": "BLACK_GREEN",
        "CAUTION": "YELLOW_BLACK",
        "CAUTIONHL": "BLACK_YELLOW",
    }


# ============================================================
# Base Form with Quit Handlers
# ============================================================
class QuitForm(npyscreen.Form):
    def set_up_handlers(self):
        super().set_up_handlers()
        self.add_handlers({curses.ascii.ETX: self.exit_editing})
        self.add_handlers({ord("q"): self.exit_editing})
        self.add_handlers({curses.KEY_RESIZE: self._handle_resize})

    def _handle_resize(self, _input):
        curses.update_lines_cols()
        self.resize()
        self.display()


# ============================================================
class Action(Enum):
    DOWNLOAD = "Download"
    WATCH = "Watch"
    SYNCPLAY = "Syncplay"


# ============================================================
# Application
# ============================================================
# TODO: auto rescale on terminal size change
class MenuApp(npyscreen.NPSApp):
    def __init__(self, url: str = ""):
        super().__init__()
        self.url = url
        self._episodes_widget = None

    def _calculate_layout(self, languages_count, providers_count):
        """Calculate optimal layout dimensions for the UI."""
        try:
            terminal_height = os.get_terminal_size().lines
        except OSError:
            terminal_height = 24

        # Calculate reserved height for all widgets (title + action + path/aniskip + language + provider + select all button + spacing)
        total_reserved_height = (
            2  # form title space
            + 4  # action widget
            + 2  # path/aniskip widget (only one visible at a time)
            + max(2, languages_count)  # language widget
            + max(2, providers_count)  # provider widget
            + 1  # select all button
            + 6  # spacing and bottom padding
        )

        max_episode_height = max(3, terminal_height - total_reserved_height)
        return max_episode_height, terminal_height

    def main(self):
        npyscreen.setTheme(CustomTheme)
        F = QuitForm(name=f"AniWorld-Downloader v.{VERSION}")

        # ============================================================
        # Get Values for series
        # ============================================================

        # Load series
        provider_meta = resolve_provider(self.url)
        series = provider_meta.series_cls(self.url)

        languages = []
        providers = []
        episodes = []

        # Only use the first season and first episode for language/provider info
        first_season = series.seasons[0]
        first_episode = first_season.episodes[0]

        # All episode URLs
        for season in series.seasons:
            for episode in season.episodes:
                episodes.append(episode.url)

        # Extract language/provider options from provider_data
        provider_data_dict = (
            first_episode.provider_data._data
            if hasattr(first_episode.provider_data, "_data")
            else first_episode.provider_data
        )

        languages = _extract_menu_languages(provider_meta.name, provider_data_dict)
        providers = _extract_menu_providers(provider_data_dict)

        if not languages:
            # Fallback to something sensible so the UI stays usable.
            # The episode model will validate on use.
            languages = [os.getenv("ANIWORLD_LANGUAGE", "German Dub")]

        if not providers:
            providers = [os.getenv("ANIWORLD_PROVIDER", "VOE")]

        # Track vertical position
        y = 2  # leave space for form title

        # --- Action ---
        is_docker = False

        if os.getenv("ANIWORLD_DOWNLOAD_PATH") == "/app/Downloads":
            is_docker = True

        action = F.add(
            npyscreen.TitleSelectOne,
            name="Action",
            values=[Action.DOWNLOAD.value]
            if is_docker
            else [Action.DOWNLOAD.value, Action.WATCH.value, Action.SYNCPLAY.value],
            value=[0],
            max_height=3,
            rely=y,
            scroll_exit=True,
        )

        # --- Path ---
        path = F.add(
            npyscreen.TitleFilenameCombo,
            name="Save Location",
            value=Path(os.getenv("ANIWORLD_DOWNLOAD_PATH")).resolve()
            or (Path("/app/Downloads") if is_docker else Path.home() / "Downloads"),
            rely=y + 4,
            max_height=2,
        )

        # --- Aniskip ---
        aniskip = F.add(
            npyscreen.TitleMultiSelect,
            name="Aniskip",
            values=["Enabled"],
            max_height=2,
            rely=y + 4,
            scroll_exit=True,
        )

        # --- Function to update visibility based on action ---
        def update_visibility():
            selected = action.get_selected_objects()
            selected_action = selected[0] if selected else Action.DOWNLOAD.value

            if selected_action in [Action.WATCH.value, Action.SYNCPLAY.value]:
                path.hidden = True
                aniskip.hidden = False
            else:  # DOWNLOAD
                path.hidden = False
                aniskip.hidden = True

            # Refresh the form layout
            F.display()

        # Attach handler: update visibility when action changes
        action.when_value_edited = update_visibility

        # Initialize visibility
        update_visibility()

        # --- Language ---
        language = F.add(
            npyscreen.TitleSelectOne,
            name="Language",
            values=languages,
            value=(
                os.getenv("ANIWORLD_LANGUAGE") in languages
                and [languages.index(os.getenv("ANIWORLD_LANGUAGE"))]
                or [0]
            ),
            max_height=max(2, len(languages)),
            rely=y + 6,
            scroll_exit=True,
        )

        # --- Provider ---
        provider = F.add(
            npyscreen.TitleSelectOne,
            name="Provider",
            values=providers,
            value=(
                os.getenv("ANIWORLD_PROVIDER") in providers
                and [providers.index(os.getenv("ANIWORLD_PROVIDER"))]
                or [0]
            ),
            max_height=max(2, len(providers)),
            rely=y + 6 + max(2, len(languages)) + 1,
            scroll_exit=True,
        )

        # --- Episodes ---
        max_episode_height, _ = self._calculate_layout(len(languages), len(providers))

        episodes_rely = y + 6 + max(2, len(languages)) + 1 + max(2, len(providers)) + 1
        episodes_widget = F.add(
            npyscreen.TitleMultiSelect,
            name="Episodes",
            values=episodes,
            rely=episodes_rely,
            max_height=max_episode_height,
            scroll_exit=True,
        )

        # Store reference for resize handling
        self._episodes_widget = episodes_widget

        # --- Select All Button ---
        select_all_button = F.add(
            npyscreen.ButtonPress,
            name="Select All",
            rely=episodes_rely + max_episode_height + 1,
        )

        def toggle_select_all():
            if len(episodes_widget.value) == len(episodes):
                episodes_widget.value = []
                select_all_button.name = "Select All"
            else:
                episodes_widget.value = list(range(len(episodes)))
                select_all_button.name = "Deselect All"
            F.display()

        select_all_button.whenPressed = toggle_select_all

        # Set up resize handler
        def handle_resize(input):
            curses.update_lines_cols()
            max_episode_height, _ = self._calculate_layout(
                len(languages), len(providers)
            )
            if self._episodes_widget:
                self._episodes_widget.max_height = max_episode_height
            F.resize()
            F.display()

        # Add resize handler
        F.add_handlers({curses.KEY_RESIZE: handle_resize})

        # --- Edit the form ---
        F.edit()

        # --- After editing, get all selected values ---
        selected_action = (
            action.get_selected_objects()[0] if action.get_selected_objects() else None
        )
        selected_path = path.value

        aniskip_enabled = aniskip.value == [0]

        selected_language = (
            language.get_selected_objects()[0]
            if language.get_selected_objects()
            else None
        )
        selected_provider = (
            provider.get_selected_objects()[0]
            if provider.get_selected_objects()
            else None
        )
        selected_episodes = (
            [episodes_widget.values[i] for i in episodes_widget.value]
            if episodes_widget.value
            else []
        )

        # --- Return and print ---
        self.result = {
            "action": selected_action,
            "path": selected_path,
            "language": selected_language,
            "provider": selected_provider,
            "episodes": selected_episodes,
            "aniskip": aniskip_enabled,
        }


# ============================================================
# Entry Point
# ============================================================
def app(url):
    try:
        app_instance = MenuApp(url)
        app_instance.run()

        # Prepare a copy of result for logging, convert Path to string
        log_result = dict(app_instance.result)
        if isinstance(log_result.get("path"), Path):
            log_result["path"] = str(log_result["path"])

        logger.debug("Menu Selection Output\n" + json.dumps(log_result, indent=4))

        # Return the result to the caller
        return app_instance.result

    except KeyboardInterrupt:
        return None
