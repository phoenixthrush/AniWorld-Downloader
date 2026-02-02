import re
import logging
import sys
from pathlib import Path
from typing import Optional, Callable
import yt_dlp

from ..models import Anime
from ..config import PROVIDER_HEADERS_D
from ..parser import arguments
from .common import get_direct_link, sanitize_filename


class QuietLogger:
    """Custom logger to suppress yt-dlp output while allowing progress hooks."""

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        # Suppress specific HLS warning that's not useful
        if "Live HLS streams are not supported" not in msg:
            logging.warning(msg)

    def error(self, msg):
        logging.error(msg)


def _create_quiet_logger():
    """Create a quiet logger for yt-dlp."""
    return QuietLogger()


def _format_bytes(bytes_value: int) -> str:
    """Format bytes to human-readable string (e.g., 1.5GiB, 500MiB)."""
    size = float(bytes_value)
    for unit in ["B", "KiB", "MiB", "GiB", "TiB"]:
        if size < 1024.0:
            return f"{size:.2f}{unit}"
        size /= 1024.0
    # Just in case :^)
    return f"{size:.2f}PiB"


def _format_episode_title(anime: Anime, episode) -> str:
    """Format episode title for logging - matches the actual filename format."""
    if episode.season == 0:
        return f"{anime.title} - Movie {episode.episode:03} - ({anime.language}).mp4"
    return f"{anime.title} - S{episode.season:02}E{episode.episode:03} - ({anime.language}).mp4"


def _get_output_filename(anime: Anime, episode, sanitized_title: str) -> str:
    """Generate output filename based on episode type."""
    if episode.season == 0:
        return (
            f"{sanitized_title} - Movie {episode.episode:03} - ({anime.language}).mp4"
        )
    return f"{sanitized_title} - S{episode.season:02}E{episode.episode:03} - ({anime.language}).mp4"


def _build_ytdl_options(
    output_path: str, anime: Anime, progress_hook: Optional[Callable] = None
) -> dict:
    """Build yt-dlp options dictionary with all necessary parameters."""
    options = {
        "nocheckcertificate": True,
        "fragment_retries": float("inf"),
        "concurrent_fragment_downloads": 4,
        "outtmpl": output_path,
        "quiet": False,  # Allow progress hooks to work
        "no_warnings": True,
        "logger": _create_quiet_logger(),  # Custom logger to suppress most output
    }

    # Add provider-specific headers
    if anime.provider in PROVIDER_HEADERS_D:
        headers = {}
        for header in PROVIDER_HEADERS_D[anime.provider]:
            if ":" in header:
                key, value = header.split(":", 1)
                headers[key.strip()] = value.strip()
        if headers:
            options["http_headers"] = headers

    # Add progress hook if provided
    if progress_hook:
        options["progress_hooks"] = [progress_hook]

    return options


def _cleanup_partial_files(output_dir: Path) -> None:
    """Clean up partial download files and empty directories."""
    if not output_dir.exists():
        return

    is_empty = True
    partial_pattern = re.compile(r"\.(part|ytdl|part-Frag\d+)$")

    for file_path in output_dir.iterdir():
        if partial_pattern.search(file_path.name):
            try:
                file_path.unlink()
            except OSError as err:
                logging.warning("Failed to remove partial file %s: %s", file_path, err)
        else:
            is_empty = False

    # Remove empty directory
    if is_empty:
        try:
            output_dir.rmdir()
        except OSError as err:
            logging.warning(
                "Failed to remove empty directory %s: %s", str(output_dir), err
            )


class CliProgressBar:
    """CLI progress bar for episode downloads."""

    def __init__(self, episode_title: str):
        self.episode_title = episode_title
        self.last_percentage = 0
        self.downloading = False

    def update(self, d):
        """Update progress based on yt-dlp progress data."""
        if d["status"] == "downloading":
            if not self.downloading:
                print(f"Starting download: {self.episode_title}")
                self.downloading = True

            # Try multiple methods to extract progress percentage
            percentage = 0.0

            # Method 1: _percent_str field
            percent_str = d.get("_percent_str")
            if percent_str:
                try:
                    percentage = float(percent_str.replace("%", ""))
                except (ValueError, TypeError):
                    pass

            # Method 2: Calculate from downloaded/total bytes
            if percentage == 0.0:
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes", 0)
                if total and total > 0:
                    percentage = (downloaded / total) * 100

            # Method 3: Use fragment info if available
            if percentage == 0.0:
                fragment_index = d.get("fragment_index", 0)
                fragment_count = d.get("fragment_count", 0)
                if fragment_count and fragment_count > 0:
                    percentage = (fragment_index / fragment_count) * 100

            # Get speed and ETA with cleaning
            speed_str = d.get("_speed_str", "N/A")
            eta_str = d.get("_eta_str", "N/A")

            # Try multiple methods to get total size
            total_bytes_str = "N/A"

            # Method 1: Use formatted string from yt-dlp (check for actual content, not just existence)
            _total_bytes_str = d.get("_total_bytes_str", "").strip()
            if _total_bytes_str and _total_bytes_str != "N/A":
                total_bytes_str = _total_bytes_str
            else:
                # Try estimate string
                _total_bytes_estimate_str = d.get(
                    "_total_bytes_estimate_str", ""
                ).strip()
                if _total_bytes_estimate_str and _total_bytes_estimate_str != "N/A":
                    total_bytes_str = _total_bytes_estimate_str
                # Method 2: Calculate from raw bytes
                elif d.get("total_bytes"):
                    total_bytes = d.get("total_bytes")
                    total_bytes_str = _format_bytes(total_bytes)
                elif d.get("total_bytes_estimate"):
                    total_bytes = d.get("total_bytes_estimate")
                    total_bytes_str = f"~{_format_bytes(total_bytes)}"

            # Clean ANSI color codes

            if speed_str != "N/A" and speed_str:
                speed_str = re.sub(r"\x1b\[[0-9;]*m", "", str(speed_str)).strip()
            else:
                speed_str = "N/A"
            if eta_str != "N/A" and eta_str:
                eta_str = re.sub(r"\x1b\[[0-9;]*m", "", str(eta_str)).strip()
            else:
                eta_str = "N/A"

            if total_bytes_str != "N/A" and total_bytes_str:
                total_bytes_str = re.sub(
                    r"\x1b\[[0-9;]*m", "", str(total_bytes_str)
                ).strip()

            # Create progress bar
            bar_width = 40
            filled_width = int(bar_width * percentage / 100)
            bar = "█" * filled_width + "░" * (bar_width - filled_width)

            # Only update if percentage changed significantly to reduce flickering
            if abs(percentage - self.last_percentage) >= 0.5:
                sys.stdout.write(
                    f"\r[{bar}] {percentage:.1f}% | Size: {total_bytes_str} | Speed: {speed_str} | ETA: {eta_str}  "
                )
                sys.stdout.flush()
                self.last_percentage = percentage

        elif d["status"] == "finished":
            print(
                "\rDownload completed successfully!                                                    "
            )
        elif d["status"] == "error":
            print(f"\rDownload failed: {d.get('error', 'Unknown error')}")


def _execute_download(
    direct_link: str,
    output_path: Path,
    anime: Anime,
    episode_title: str = "",
    web_progress_callback: Optional[Callable] = None,
) -> bool:
    """Execute download using yt-dlp Python API with progress tracking."""
    try:
        # Create CLI progress bar
        cli_progress = CliProgressBar(episode_title)

        def combined_progress_hook(d):
            """Combined progress hook for both CLI and web progress."""
            # Update CLI progress
            cli_progress.update(d)

            # Update web progress if callback provided
            if web_progress_callback:
                try:
                    web_progress_callback(d)
                except KeyboardInterrupt:
                    # Re-raise KeyboardInterrupt to stop download
                    raise
                except Exception as e:
                    logging.warning(f"Web progress callback error: {e}")

        # Build yt-dlp options
        options = _build_ytdl_options(str(output_path), anime, combined_progress_hook)

        # Execute download with yt-dlp
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([direct_link])

        print("")  # New line after progress bar
        return True

    except yt_dlp.DownloadError as e:
        logging.error(f"yt-dlp download error: {e}")
        print(f"\n❌ Download failed: {e}")
        return False
    except KeyboardInterrupt:
        logging.info("Download interrupted by user")
        print("\n⏹️ Download interrupted by user")
        _cleanup_partial_files(output_path.parent)
        raise
    except Exception as e:
        logging.error(f"Unexpected download error: {e}")
        print(f"\n❌ Unexpected error: {e}")
        return False


def download(
    anime: Anime,
    web_progress_callback: Optional[Callable] = None,
    output_dir: Optional[str] = None,
) -> None:
    """Download all episodes of an anime."""
    sanitized_anime_title = sanitize_filename(anime.title)

    for episode in anime:
        episode_title = _format_episode_title(anime, episode)

        # Get direct link
        direct_link = get_direct_link(episode, episode_title)
        if not direct_link:
            logging.warning(
                'Something went wrong with "%s".\nNo direct link found.', episode_title
            )
            continue

        # Handle direct link only mode
        if arguments.only_direct_link:
            print(episode_title)
            print(f"{direct_link}\n")
            continue

        # Generate output path
        output_file = _get_output_filename(anime, episode, sanitized_anime_title)

        # Use provided output_dir or fall back to arguments.output_dir
        base_dir = Path(output_dir) if output_dir else Path(arguments.output_dir)
        output_path = base_dir / sanitized_anime_title / output_file

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle command only mode - build equivalent yt-dlp command for display
        if arguments.only_command:
            _options = _build_ytdl_options(str(output_path), anime)
            # Convert back to command format for display
            command = ["yt-dlp", direct_link]
            command.extend(["--no-check-certificate"])
            command.extend(["--fragment-retries", "infinite"])
            command.extend(["--concurrent-fragments", "4"])
            command.extend(["-o", str(output_path)])
            command.extend(["--quiet", "--no-warnings"])

            # Add headers if any
            if anime.provider in PROVIDER_HEADERS_D:
                for header in PROVIDER_HEADERS_D[anime.provider]:
                    command.extend(["--add-header", header])

            print(
                f"\n{anime.title} - S{episode.season}E{episode.episode} - ({anime.language}):"
            )
            print(" ".join(command))
            continue

        # Execute download
        _execute_download(
            direct_link, output_path, anime, episode_title, web_progress_callback
        )
