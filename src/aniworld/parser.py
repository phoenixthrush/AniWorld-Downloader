import argparse
import importlib
import json
import logging
import os
import platform
import random
import shutil
import subprocess
import sys
from functools import lru_cache
from typing import Dict, List, Optional, Callable

import requests

from .common import (
    download_mpv,
    download_syncplay,
    remove_anime4k,
    remove_mpv_scripts,
)
from .extractors.provider.hanime import get_direct_link_from_hanime
from .anime4k import download_anime4k
from . import config


class CaseInsensitiveChoices:
    """Case-insensitive argument choice validator for argparse."""

    def __init__(self, choices: List[str]) -> None:
        """
        Initialize with a list of valid choices.

        Args:
            choices: List of valid choice strings
        """
        self.choices = choices
        self.normalized = {c.lower(): c for c in choices}

    def __call__(self, value: str) -> str:
        """
        Validate and normalize the input value.

        Args:
            value: Input value to validate

        Returns:
            Normalized choice string

        Raises:
            argparse.ArgumentTypeError: If value is not a valid choice
        """
        key = value.lower()
        if key in self.normalized:
            return self.normalized[key]
        raise argparse.ArgumentTypeError(
            f"invalid choice: {value} (choose from {', '.join(self.choices)})"
        )


@lru_cache(maxsize=128)
def get_random_anime_slug(genre: str) -> Optional[str]:
    """
    Fetch a random anime slug from the specified genre.

    Args:
        genre: The genre to search for (e.g., "all", "Drama", "Action")

    Returns:
        Random anime slug or None if no anime found or error occurred
    """
    if not genre:
        genre = "all"

    url = f"{config.ANIWORLD_TO}/ajax/randomGeneratorSeries"
    data = {"productionStart": "all", "productionEnd": "all", "genres[]": genre}
    headers = {"User-Agent": config.RANDOM_USER_AGENT}

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=config.DEFAULT_REQUEST_TIMEOUT
        )
        response.raise_for_status()

        anime_list = response.json()
        if not anime_list:
            logging.warning("No anime found for genre: %s", genre)
            return None

        random_anime = random.choice(anime_list)
        logging.debug("Selected random anime: %s", random_anime)

        return random_anime.get("link")

    except requests.RequestException as err:
        logging.error("Network request failed for genre '%s': %s", genre, err)
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        logging.error("Error processing response data for genre '%s': %s", genre, err)
    except Exception as err:
        logging.error(
            "Unexpected error getting random anime for genre '%s': %s", genre, err
        )

    return None


def _add_general_arguments(parser: argparse.ArgumentParser) -> None:
    """Add general command-line arguments to the parser."""
    general_opts = parser.add_argument_group("General Options")
    general_opts.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug mode for detailed logs.",
    )
    general_opts.add_argument(
        "-U",
        "--update",
        type=str,
        choices=["mpv", "yt-dlp", "syncplay", "all"],
        help="Update specified tools (mpv, yt-dlp, syncplay, or all).",
    )
    general_opts.add_argument(
        "-u", "--uninstall", action="store_true", help="Perform self-uninstallation."
    )
    general_opts.add_argument(
        "-v", "--version", action="store_true", help="Display version information."
    )


def _add_search_arguments(parser: argparse.ArgumentParser) -> None:
    """Add search-related command-line arguments to the parser."""
    search_opts = parser.add_argument_group("Search Options")
    search_opts.add_argument(
        "-s",
        "--slug",
        type=str,
        help="Specify a search slug (e.g., demon-slayer-kimetsu-no-yaiba).",
    )


def _add_episode_arguments(parser: argparse.ArgumentParser) -> None:
    """Add episode-related command-line arguments to the parser."""
    episode_opts = parser.add_argument_group("Episode Options")
    episode_opts.add_argument(
        "-e", "--episode", type=str, nargs="+", help="Specify one or more episode URLs."
    )
    episode_opts.add_argument(
        "-f", "--episode-file", type=str, help="Provide a file containing episode URLs."
    )
    episode_opts.add_argument(
        "-lf",
        "--local-episodes",
        type=str,
        nargs="+",
        help="Use local MP4 files for episodes instead of URLs.",
    )
    episode_opts.add_argument(
        "-pl",
        "--provider-link",
        type=str,
        nargs="+",
        help="Specify one or more provider episode urls.",
    )


def _add_action_arguments(parser: argparse.ArgumentParser) -> None:
    """Add action-related command-line arguments to the parser."""
    action_opts = parser.add_argument_group("Action Options")
    action_opts.add_argument(
        "-a",
        "--action",
        type=CaseInsensitiveChoices(["Watch", "Download", "Syncplay"]),
        default=config.DEFAULT_ACTION,
        help="Specify the action to perform.",
    )
    action_opts.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=config.DEFAULT_DOWNLOAD_PATH,
        help="Set the download directory (e.g., /path/to/downloads).",
    )
    action_opts.add_argument(
        "-L",
        "--language",
        type=CaseInsensitiveChoices(
            ["German Dub", "English Sub", "German Sub", "English Dub"]
        ),
        default=config.DEFAULT_LANGUAGE,
        help="Specify the language for playback or download.",
    )
    action_opts.add_argument(
        "-p",
        "--provider",
        type=CaseInsensitiveChoices(config.SUPPORTED_PROVIDERS),
        help="Specify the preferred provider.",
    )


def _add_anime4k_arguments(parser: argparse.ArgumentParser) -> None:
    """Add Anime4K-related command-line arguments to the parser."""
    anime4k_opts = parser.add_argument_group("Anime4K Options")
    anime4k_opts.add_argument(
        "-A",
        "--anime4k",
        type=CaseInsensitiveChoices(["High", "Low", "Remove"]),
        help="Set Anime4K mode (High, Low, or Remove for performance tuning).",
    )


def _add_syncplay_arguments(parser: argparse.ArgumentParser) -> None:
    """Add Syncplay-related command-line arguments to the parser."""
    syncplay_opts = parser.add_argument_group("Syncplay Options")
    syncplay_opts.add_argument(
        "-sH", "--hostname", type=str, help="Set the Syncplay server hostname."
    )
    syncplay_opts.add_argument(
        "-sU", "--username", type=str, help="Set the Syncplay username."
    )
    syncplay_opts.add_argument(
        "-sR", "--room", type=str, help="Specify the Syncplay room name."
    )
    syncplay_opts.add_argument(
        "-sP", "--password", type=str, nargs="+", help="Set the Syncplay room password."
    )


def _add_web_ui_arguments(parser: argparse.ArgumentParser) -> None:
    """Add Web UI related command-line arguments to the parser."""
    web_opts = parser.add_argument_group("Web UI Options")
    web_opts.add_argument(
        "-w",
        "--web-ui",
        action="store_true",
        help="Start Flask web interface instead of CLI.",
    )
    web_opts.add_argument(
        "-wP",
        "--web-port",
        type=int,
        default=5000,
        help="Specify the port for the Flask web interface (default: 5000).",
    )
    web_opts.add_argument(
        "-wA",
        "--enable-web-auth",
        action="store_true",
        help="Enable authentication for web interface with user management.",
    )
    web_opts.add_argument(
        "-wN",
        "--no-browser",
        action="store_true",
        help="Disable automatic browser opening when starting web interface.",
    )
    web_opts.add_argument(
        "-wE",
        "--web-expose",
        action="store_true",
        help="Bind web interface to 0.0.0.0 instead of localhost for external access.",
    )


def _add_miscellaneous_arguments(parser: argparse.ArgumentParser) -> None:
    """Add miscellaneous command-line arguments to the parser."""
    misc_opts = parser.add_argument_group("Miscellaneous Options")
    misc_opts.add_argument(
        "-k",
        "--aniskip",
        action="store_true",
        help="Skip anime intros and outros using Aniskip.",
    )
    misc_opts.add_argument(
        "-K",
        "--keep-watching",
        action="store_true",
        help="Automatically continue to the next episodes after the selected one.",
    )
    misc_opts.add_argument(
        "-r",
        "--random-anime",
        type=str,
        nargs="*",
        help='Play a random anime (default genre is "all", e.g., Drama).\n'
        f'All genres can be found here: "{config.ANIWORLD_TO}/random"',
    )
    misc_opts.add_argument(
        "-D",
        "--only-direct-link",
        action="store_true",
        help="Output only the direct streaming link.",
    )
    misc_opts.add_argument(
        "-C",
        "--only-command",
        action="store_true",
        help="Output only the execution command.",
    )


def _handle_uninstall() -> None:
    """Handle application uninstallation."""
    try:
        print(f"Removing: {config.DEFAULT_APPDATA_PATH}")
        if os.path.exists(config.DEFAULT_APPDATA_PATH):
            shutil.rmtree(config.DEFAULT_APPDATA_PATH)

        remove_anime4k()
        remove_mpv_scripts()

        if sys.platform.startswith("win"):
            # Use cmd /c to run the command chain
            cmd = ["cmd", "/c", "timeout 3 >nul & pip uninstall -y aniworld"]
        else:
            cmd = ["pip", "uninstall", "-y", "aniworld"]

        print("pip uninstall -y aniworld")
        with subprocess.Popen(
            cmd,
            shell=False,
            creationflags=subprocess.CREATE_NEW_CONSOLE
            if sys.platform.startswith("win")
            else 0,
        ):
            pass
    except Exception as err:
        logging.error("Error during uninstallation: %s", err)
        sys.exit(1)

    sys.exit(0)


def _handle_version() -> None:
    """Handle version information display."""
    cowsay = Rf"""
_____________________________
< AniWorld-Downloader v.{config.VERSION} >
-----------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
"""
    if not config.IS_NEWEST_VERSION:
        cowsay += (
            f"\nYour version is outdated.\n"
            f"Please update to the latest version (v.{config.LATEST_VERSION})."
        )
    else:
        cowsay += "\nYou are on the latest version."

    print(cowsay.strip())
    sys.exit(0)


def _handle_provider_links(args: argparse.Namespace) -> None:
    """Handle provider link processing."""
    if not args.provider_link:
        return

    # Validate provider links
    invalid_links = [link for link in args.provider_link if not link.startswith("http")]
    if invalid_links:
        logging.error("Invalid provider episode URLs: %s", ", ".join(invalid_links))
        sys.exit(1)

    # Handle hanime.tv links specially
    hanime_links = [
        link
        for link in args.provider_link
        if link.startswith("https://hanime.tv/videos/")
    ]

    if hanime_links:
        # Process hanime.tv links
        for link in hanime_links:
            try:
                direct_link = get_direct_link_from_hanime(link)
                if direct_link:
                    print(f"-> {link}")
                    print(f'"{direct_link}"')
                    print("-" * 40)
                else:
                    logging.error(
                        "Could not extract direct link from hanime URL: %s", link
                    )
            except Exception as err:
                logging.error("Error processing hanime link '%s': %s", link, err)

        # Remove processed hanime links from provider_link list
        args.provider_link = [
            link
            for link in args.provider_link
            if not link.startswith("https://hanime.tv/videos/")
        ]

    if not args.provider_link:
        sys.exit(0)

    # Validate provider is specified
    if not args.provider:
        logging.error("Provider must be specified when using provider links.")
        sys.exit(1)

    logging.info("Using provider: %s", args.provider)

    # Process provider links
    if args.provider in config.SUPPORTED_PROVIDERS:
        try:
            module = importlib.import_module("aniworld.extractors")
            func = getattr(module, f"get_direct_link_from_{args.provider.lower()}")

            for provider_episode in args.provider_link:
                direct_link = func(provider_episode)

                action_map = {
                    "Download": config.YTDLP_PATH,
                    "Watch": config.MPV_PATH,
                    "Syncplay": config.SYNCPLAY_PATH,
                }
                action = action_map.get(args.action)
                if not action:
                    raise ValueError(f"Invalid action: {args.action}")

                cmd = [action, direct_link]
                # Add provider headers if present
                if (
                    args.provider in config.PROVIDER_HEADERS_D
                    and config.PROVIDER_HEADERS_D.get(args.provider)
                ):
                    header = (
                        "--add-header"
                        if args.action == "Download"
                        else "--http-header-fields"
                    )
                    for h in config.PROVIDER_HEADERS_D[args.provider]:
                        cmd.extend([header, h])

                print(f"-> {provider_episode}")
                subprocess.run(cmd, check=True)
                print("-" * 40)
        except KeyboardInterrupt:
            pass
        except Exception as err:
            logging.error("Error processing provider links: %s", err)
            sys.exit(1)

    sys.exit(0)


def _update_yt_dlp() -> None:
    """Update yt-dlp to the latest version."""
    try:
        logging.info("Upgrading yt-dlp...")
        yt_dlp_update_command = ["pip", "install", "-U", "yt-dlp"]

        logging.debug("Running Command: %s", yt_dlp_update_command)
        subprocess.run(
            yt_dlp_update_command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info("yt-dlp updated successfully")
    except subprocess.CalledProcessError as err:
        logging.error("Failed to update yt-dlp: %s", err)
    except Exception as err:
        logging.error("Unexpected error updating yt-dlp: %s", err)


def _update_all_tools() -> None:
    """Update all supported tools."""
    try:
        logging.info("Updating all tools...")
        download_mpv(update=True)
        _update_yt_dlp()
        download_syncplay(update=True)
        logging.info("All tools updated successfully")
    except Exception as err:
        logging.error("Error updating tools: %s", err)


def _handle_updates(update_type: str) -> None:
    """Handle tool updates."""
    update_actions: Dict[str, Callable[[], None]] = {
        "mpv": lambda: download_mpv(update=True),
        "yt-dlp": _update_yt_dlp,
        "syncplay": lambda: download_syncplay(update=True),
        "all": _update_all_tools,
    }

    action = update_actions.get(update_type)
    if action:
        try:
            action()
        except Exception as err:
            logging.error("Error during %s update: %s", update_type, err)
    else:
        logging.error("Invalid update option: %s", update_type)


def _open_terminal_with_command(command: str) -> None:
    """Open a terminal with the specified command (Linux)."""
    if not os.environ.get("DISPLAY"):
        print(
            "It looks like you are on a headless machine! "
            "For advanced log look in your temp folder!"
        )
        return

    terminal_emulators = [
        (
            "gnome-terminal",
            ["gnome-terminal", "--", "bash", "-c", f"{command}; exec bash"],
        ),
        ("xterm", ["xterm", "-hold", "-e", command]),
        ("konsole", ["konsole", "--hold", "-e", command]),
    ]

    for terminal, cmd in terminal_emulators:
        try:
            with subprocess.Popen(cmd):
                return
        except FileNotFoundError:
            logging.debug("%s not found, trying next option.", terminal)
        except subprocess.SubprocessError as err:
            logging.error("Error opening terminal with %s: %s", terminal, err)

    logging.error(
        "No supported terminal emulator found. "
        "Install gnome-terminal, xterm, or konsole."
    )


def _handle_debug_mode() -> None:
    """Handle debug mode setup."""
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("=============================================")
    logging.debug("   Welcome to AniWorld Downloader v.%s!   ", config.VERSION)
    logging.debug("=============================================\n")

    system = platform.system()

    try:
        if system == "Darwin":
            darwin_open_debug_log = [
                "osascript",
                "-e",
                'tell application "Terminal" to do script "trap exit SIGINT; '
                'tail -f -n +1 $TMPDIR/aniworld.log" activate',
            ]
            logging.debug("Running Command: %s", darwin_open_debug_log)
            subprocess.run(darwin_open_debug_log, check=True)

        elif system == "Windows":
            windows_open_debug_log = [
                "cmd",
                "/c",
                'start',
                'cmd',
                '/c',
                'powershell -NoExit -c Get-Content -Wait "$env:TEMP\\aniworld.log"'
            ]
            logging.debug("Running Command: %s", windows_open_debug_log)
            # shell=True required for start command in windows? 
            # Actually 'start' is a shell built-in.
            # To avoid shell=True we invoked cmd /c start ...
            subprocess.run(windows_open_debug_log, shell=False, check=True)

        elif system == "Linux":
            _open_terminal_with_command("tail -f -n +1 /tmp/aniworld.log")

    except subprocess.CalledProcessError as err:
        logging.error("Failed to start tailing the log file: %s", err)
    except Exception as err:
        logging.error("Unexpected error setting up debug mode: %s", err)


def _setup_default_provider(args: argparse.Namespace) -> None:
    """Set up default provider if none specified."""
    if args.provider is None:
        config.USES_DEFAULT_PROVIDER = True
        args.provider = (
            config.DEFAULT_PROVIDER_DOWNLOAD
            if args.action == "Download"
            else config.DEFAULT_PROVIDER_WATCH
        )


def _handle_hanime_episodes(args: argparse.Namespace) -> None:
    """Handle hanime.tv URLs in episode arguments by moving them to provider links."""
    if not args.episode:
        return

    # Find hanime.tv URLs in episode arguments
    hanime_episodes = [
        ep for ep in args.episode if ep.startswith("https://hanime.tv/videos/")
    ]

    if not hanime_episodes:
        return

    # Remove hanime.tv URLs from episode list
    args.episode = [
        ep for ep in args.episode if not ep.startswith("https://hanime.tv/videos/")
    ]

    # Add them to provider_link list
    if not args.provider_link:
        args.provider_link = []
    args.provider_link.extend(hanime_episodes)

    logging.info(
        "Moved %d hanime.tv URL(s) to provider link processing", len(hanime_episodes)
    )


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the AniWorld-Downloader.

    Returns:
        Parsed command-line arguments
    """
    parser = argparse.ArgumentParser(
        description="Parse command-line arguments for anime streaming, "
        "downloading, and playback management."
    )

    # Add all argument groups
    _add_general_arguments(parser)
    _add_search_arguments(parser)
    _add_episode_arguments(parser)
    _add_action_arguments(parser)
    _add_anime4k_arguments(parser)
    _add_syncplay_arguments(parser)
    _add_web_ui_arguments(parser)
    _add_miscellaneous_arguments(parser)

    args = parser.parse_args()

    # Handle immediate exit actions
    if args.uninstall:
        _handle_uninstall()

    if args.version:
        _handle_version()

    if args.anime4k:
        download_anime4k(args.anime4k)

    # Handle hanime.tv URLs in episode arguments (move them to provider links)
    _handle_hanime_episodes(args)

    # Handle provider links
    _handle_provider_links(args)

    # Handle updates
    if args.update:
        _handle_updates(args.update)

    # Handle random anime
    if args.random_anime is not None:
        genre = args.random_anime[0] if args.random_anime else "all"
        args.slug = get_random_anime_slug(genre)

    # Set up default provider
    _setup_default_provider(args)

    # Handle debug mode
    if args.debug:
        _handle_debug_mode()

    return args


arguments = parse_arguments()

if __name__ == "__main__":
    pass
