import logging
import subprocess
from typing import List, Optional

from ..parser import arguments
from ..aniskip import aniskip
from ..models import Anime

# Set of characters not allowed in filenames on most filesystems
INVALID_PATH_CHARS = set(r'<>:"/\\|?*')


def sanitize_filename(filename: str) -> str:
    """
    Remove invalid characters from a filename.
    Used to ensure compatibility across different OS filesystems.
    """
    return "".join(char for char in filename if char not in INVALID_PATH_CHARS)


def format_episode_title(anime, episode) -> str:
    """
    Create a formatted title string for logging or printing.
    Example: "Naruto - S01E03 - (German Sub):"
    """
    return f"{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"


def get_media_title(anime, episode, sanitized_title: str) -> str:
    """
    Create the media filename title based on episode type.
    If it's a movie (season == 0), format differently.
    """
    if episode.season == 0:
        return f"{sanitized_title} - Movie {episode.episode:03} - ({anime.language})"
    return f"{sanitized_title} - S{episode.season:02}E{episode.episode:03} - ({anime.language})"


def get_direct_link(episode, episode_title: str) -> Optional[str]:
    """
    Try to get a direct link for the episode.
    Log a warning and return None if it fails.
    """
    try:
        return episode.get_direct_link()
    except Exception as err:
        logging.warning(
            'Something went wrong with "%s".\nError while trying to find a direct link: %s',
            episode_title,
            err,
        )
        return None


def execute_command(command: List[str]) -> None:
    """Execute command or print it if in command-only mode."""
    if arguments.only_command:
        print("\n" + " ".join(str(item) for item in command))
        return

    try:
        # Redact sensitive info for logging
        log_command = [
            "***" if i > 0 and command[i-1] in ("--password", "-p") else str(arg)
            for i, arg in enumerate(command)
        ]
        logging.debug("Running Command:\n%s", log_command)
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as err:
        # Redact sensitive info for error logging as well
        log_command = [
            "***" if i > 0 and command[i-1] in ("--password", "-p") else str(arg)
            for i, arg in enumerate(command)
        ]
        logging.error("Error running command: %s\nCommand: %s", err, " ".join(log_command))
    except KeyboardInterrupt:
        logging.info("Syncplay execution interrupted by user")
        raise


def get_aniskip_data(anime: Anime, episode) -> Optional[str]:
    """Get aniskip data for episode if enabled."""
    if not anime.aniskip:
        return None

    try:
        return aniskip(
            anime.title,
            episode.episode,
            episode.season,
            episode.season_episode_count[episode.season],
        )
    except Exception as err:
        logging.warning("Failed to get aniskip data for %s: %s", anime.title, err)
        return None
