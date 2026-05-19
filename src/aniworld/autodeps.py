import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import List

PLATFORM = platform.system()

try:
    from .common import fetch_github_asset_urls
    from .config import GLOBAL_SESSION
    from .logger import get_logger

except ImportError:
    from aniworld.common import fetch_github_asset_urls
    from aniworld.config import GLOBAL_SESSION
    from aniworld.logger import get_logger


# -----------------------------
# MPV
# -----------------------------
def get_mpv_release_urls() -> dict[str, list[str]]:
    """
    Fetch all Windows MPV release URLs, separated into v3 and non-v3 builds.

    Returns:
        {
            "v3": [...],      # all v3 release URLs
            "non_v3": [...]   # all non-v3 release URLs
        }
    """
    repo = "shinchiro/mpv-winbuild-cmake"

    patterns = {
        "v3": r"mpv-x86_64-v3-\d{8}-git-[a-f0-9]+\.7z$",
        "non_v3": r"mpv-x86_64-(?!v3-)\d{8}-git-[a-f0-9]+\.7z$",
    }

    urls: dict[str, list[str]] = {}

    for key, pattern in patterns.items():
        urls[key] = fetch_github_asset_urls(repo, pattern)

    return urls


def get_mpv_windows_url(v3: bool = False) -> str:
    """
    Get a single Windows MPV URL.

    Args:
        v3: whether to get the v3 build (default False → non-v3)
    """
    all_urls = get_mpv_release_urls()
    key = "v3" if v3 else "non_v3"
    return all_urls.get(key, [None])[0]  # return first match or None


# -----------------------------
# FFmpeg
# -----------------------------
def get_ffmpeg_windows_url() -> str:
    """Get the latest Windows FFmpeg full-build ZIP URL from BtbN/FFmpeg-Builds."""
    repo = "BtbN/FFmpeg-Builds"
    pattern = r"ffmpeg-master-latest-win64-gpl\.zip$"
    urls = fetch_github_asset_urls(repo, pattern)
    return urls[0] if urls else None


# -----------------------------
# Syncplay
# -----------------------------
def get_syncplay_release_url() -> List[str]:
    """Fetch the URLs for the latest Windows Syncplay portable ZIP release."""
    repo = "Syncplay/syncplay"
    portable_pattern = r"Syncplay[_-]\d+(?:\.\d+)*_Portable\.zip$"
    return fetch_github_asset_urls(repo, portable_pattern)


def get_syncplay_windows_url() -> str:
    """Get Windows Syncplay URL (first match)."""
    urls = get_syncplay_release_url()
    return urls[0] if urls else None


# -----------------------------
# Dependencies
# -----------------------------
deps = {
    "mpv": {
        "Windows": {"package": "mpv.net", "url": None},
        "Linux": {"package": "mpv"},
        "Darwin": {"package": "mpv"},
    },
    "syncplay": {
        "Windows": {"package": "Syncplay.Syncplay", "url": None},
        "Linux": {"package": "syncplay"},
        "Darwin": {"package": "syncplay"},
    },
    "iina": {"Darwin": {"package": "iina"}},
    "7z": {"Windows": {"url": "https://7-zip.org/a/7zr.exe"}},
    "ffmpeg": {
        "Windows": {"package": "Gyan.FFmpeg", "url": None},
        "Linux": {"package": "ffmpeg"},
        "Darwin": {"package": "ffmpeg"},
    },
}


# -----------------------------
# Dependency Manager
# -----------------------------
class DependencyManager:
    """Manage binaries with system package manager or direct download."""

    def __init__(self, install_folder=None):
        self.deps = deps
        self.install_folder = Path(
            install_folder
            or os.getenv("ANIWORLD_INSTALL_FOLDER", Path.home() / ".aniworld")
        )
        self.install_folder.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger(__name__)
        self.logger.debug(f"Dependency folder: {self.install_folder}")

    def fetch_binary(self, name: str) -> Path:
        dep_info = self.deps.get(name, {}).get(PLATFORM, {})

        # System-wide first
        sys_path = shutil.which(name)
        if sys_path:
            self.logger.debug(f"{name} found system-wide at {sys_path}")
            return Path(sys_path)

        url = dep_info.get("url")

        # Lazy resolution for MPV Windows URL
        if name == "mpv" and PLATFORM == "Windows" and not url:
            url = get_mpv_windows_url()
            dep_info["url"] = url

        # Lazy resolution for FFmpeg Windows URL
        if name == "ffmpeg" and PLATFORM == "Windows" and not url:
            url = get_ffmpeg_windows_url()
            dep_info["url"] = url

        local_path = self.install_folder / Path(url).name if url else None

        # Local folder
        if local_path and local_path.exists():
            self.logger.debug(f"{name} found in {self.install_folder}")
            return local_path

        # Package manager
        if self._install_with_package_manager(name):
            sys_path_after = shutil.which(name)
            if sys_path_after:
                return Path(sys_path_after)
            if local_path and local_path.exists():
                return local_path

        # Download fallback
        self.logger.debug(f"Downloading {name} for {PLATFORM} from {url}...")
        resp = GLOBAL_SESSION.get(url, stream=True)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if PLATFORM != "Windows":
            local_path.chmod(0o755)

        self.logger.debug(f"{name} downloaded to {local_path}")
        return local_path

    def _install_with_package_manager(self, name: str) -> bool:
        dep_info = self.deps.get(name, {}).get(PLATFORM, {})
        pkg_name = dep_info.get("package")
        if not pkg_name:
            return False

        try:
            if PLATFORM == "Windows":
                subprocess.run(
                    ["winget", "install", "-e", "--id", pkg_name, "-h"], check=True
                )
            elif PLATFORM == "Darwin":
                subprocess.run(["brew", "install", pkg_name], check=True)
            else:
                if shutil.which("apt"):
                    subprocess.run(["sudo", "apt", "update"], check=True)
                    subprocess.run(
                        ["sudo", "apt", "install", "-y", pkg_name], check=True
                    )
                elif shutil.which("pacman"):
                    subprocess.run(["sudo", "pacman", "-Sy", pkg_name], check=True)
                else:
                    return False

            self.logger.debug(f"{name} installed via package manager on {PLATFORM}")
            return True

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            self.logger.debug(f"Package manager failed for {name} on {PLATFORM}: {e}")
            return False


# -----------------------------
# Player paths
# -----------------------------
def get_player_path() -> Path:
    manager = DependencyManager()
    use_iina = os.getenv("ANIWORLD_USE_IINA") == "1"
    use_aniskip = os.getenv("ANIWORLD_ANISKIP") == "1"

    if PLATFORM == "Darwin" and use_iina and not use_aniskip:
        return manager.fetch_binary("iina")

    return manager.fetch_binary("mpv")


def get_syncplay_path() -> Path:
    if PLATFORM == "Darwin":
        syncplay_path = Path("/Applications/Syncplay.app/Contents/MacOS/Syncplay")
        if syncplay_path.exists():
            return syncplay_path
    manager = DependencyManager()
    return manager.fetch_binary("syncplay")


# -----------------------------
# Testing
# -----------------------------
def _ensure_xvfb():
    """On headless Linux: install Xvfb if missing and start a virtual display on :99."""
    if PLATFORM != "Linux":
        return
    if os.environ.get("DISPLAY"):
        return
    _log = get_logger(__name__)
    if not shutil.which("Xvfb"):
        _log.info("Xvfb not found — installing via apt...")
        try:
            subprocess.run(["sudo", "apt-get", "install", "-y", "xvfb"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            _log.warning(f"Could not install Xvfb: {e}")
            return
    _log.info("No DISPLAY found — starting Xvfb on :99")
    subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.environ["DISPLAY"] = ":99"


def ensure_patchright_chromium():
    """Install the patchright Chromium browser if not already present."""
    import sys
    _log = get_logger(__name__)
    try:
        import patchright  # noqa: F401
    except ImportError:
        _log.debug("patchright not installed, skipping chromium check")
        return

    _ensure_xvfb()
    try:
        _log.debug("Ensuring patchright chromium is installed...")
        _log.info("Installing patchright chromium (this may take a moment)...")
        subprocess.run(
            [sys.executable, "-m", "patchright", "install", "chromium"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log.debug("patchright chromium is ready")
        _log.info("patchright chromium is ready")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _log.warning(f"patchright chromium install failed: {e}")


if __name__ == "__main__":
    print(get_player_path())
    print(get_syncplay_path())
