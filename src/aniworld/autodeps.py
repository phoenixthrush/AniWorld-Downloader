import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

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
        "Windows": {
            "package": "mpv.net",
            "url": None,
            "binary_names": ["mpv.exe", "mpv"],
        },
        "Linux": {"package": "mpv"},
        "Darwin": {"package": "mpv"},
    },
    "syncplay": {
        "Windows": {
            "package": "Syncplay.Syncplay",
            "url": None,
            "binary_names": ["Syncplay.exe", "syncplay.exe", "syncplay"],
        },
        "Linux": {"package": "syncplay"},
        "Darwin": {"package": "syncplay"},
    },
    "iina": {"Darwin": {"package": "iina"}},
    "7z": {"Windows": {"url": "https://7-zip.org/a/7zr.exe"}},
    "ffmpeg": {
        "Windows": {
            "package": "Gyan.FFmpeg",
            "url": None,
            "binary_names": ["ffmpeg.exe", "ffmpeg"],
        },
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
        configured_install_folder = (
            install_folder
            or os.getenv("ANIWORLD_INSTALL_FOLDER")
            or (Path.home() / ".aniworld")
        )
        configured_install_folder = Path(configured_install_folder).expanduser()
        if not configured_install_folder.is_absolute():
            configured_install_folder = Path.home() / configured_install_folder
        self.install_folder = configured_install_folder.resolve()
        self.install_folder.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger(__name__)
        self.logger.debug(f"Dependency folder: {self.install_folder}")

    def _prepend_to_path(self, binary_path: Path) -> None:
        binary_dir = str(binary_path.parent)
        current_path = os.environ.get("PATH", "")
        path_entries = current_path.split(os.pathsep) if current_path else []
        if binary_dir not in path_entries:
            os.environ["PATH"] = (
                binary_dir
                if not current_path
                else os.pathsep.join([binary_dir, current_path])
            )

    def _find_binary_in_dir(
        self, search_dir: Path, binary_names: list[str]
    ) -> Optional[Path]:
        for binary_name in binary_names:
            direct_match = search_dir / binary_name
            if direct_match.exists():
                return direct_match

            matches = sorted(
                search_dir.rglob(binary_name),
                key=lambda path: (len(path.parts), str(path).lower()),
            )
            if matches:
                return matches[0]

        return None

    def _find_binary_on_path(self, name: str, dep_info: dict) -> Optional[Path]:
        binary_names = [name, *(dep_info.get("binary_names") or [])]

        for binary_name in dict.fromkeys(binary_names):
            sys_path = shutil.which(binary_name)
            if sys_path:
                return Path(sys_path)

        return None

    def _find_local_binary(self, name: str, dep_info: dict) -> Optional[Path]:
        binary_names = dep_info.get("binary_names") or [name]
        binary_path = self._find_binary_in_dir(self.install_folder, binary_names)
        if binary_path:
            self._prepend_to_path(binary_path)
        return binary_path

    def _extract_archive(self, archive_path: Path) -> Path:
        extract_dir = self.install_folder / archive_path.stem
        extract_dir.mkdir(parents=True, exist_ok=True)

        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_dir)
            return extract_dir

        if archive_path.suffix.lower() == ".7z":
            seven_zip_path = self.fetch_binary("7z", prompt_user=False)
            subprocess.run(
                [
                    str(seven_zip_path),
                    "x",
                    str(archive_path),
                    f"-o{extract_dir}",
                    "-y",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return extract_dir

        raise ValueError(f"Unsupported archive format: {archive_path}")

    def _confirm_install(self, message: str, default: bool = True) -> bool:
        if not sys.stdin or not sys.stdin.isatty():
            return False

        prompt = "[Y/n]" if default else "[y/N]"
        reply = input(f"{message} {prompt} ").strip().lower()
        if not reply:
            return default
        return reply in {"y", "yes"}

    def _resolve_download_url(self, name: str, dep_info: dict) -> Optional[str]:
        url = dep_info.get("url")

        if name == "mpv" and PLATFORM == "Windows" and not url:
            url = get_mpv_windows_url()
            dep_info["url"] = url

        if name == "syncplay" and PLATFORM == "Windows" and not url:
            url = get_syncplay_windows_url()
            dep_info["url"] = url

        if name == "ffmpeg" and PLATFORM == "Windows" and not url:
            url = get_ffmpeg_windows_url()
            dep_info["url"] = url

        return url

    def _download_binary(self, name: str, dep_info: dict, url: str) -> Path:
        local_path = self.install_folder / Path(url).name

        self.logger.debug(f"Downloading {name} for {PLATFORM} from {url}...")
        resp = GLOBAL_SESSION.get(url, stream=True)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        if PLATFORM != "Windows":
            local_path.chmod(0o755)

        self.logger.debug(f"{name} downloaded to {local_path}")
        resolved_binary = self._resolve_local_binary(name, dep_info, local_path)
        return resolved_binary or local_path

    def _resolve_local_binary(
        self, name: str, dep_info: dict, local_path: Optional[Path]
    ):
        if not local_path or not local_path.exists():
            return None

        binary_names = dep_info.get("binary_names") or [name]

        if local_path.suffix.lower() in {".zip", ".7z"}:
            extract_dir = self.install_folder / local_path.stem
            binary_path = self._find_binary_in_dir(extract_dir, binary_names)

            if not binary_path:
                extract_dir = self._extract_archive(local_path)
                binary_path = self._find_binary_in_dir(extract_dir, binary_names)

            if not binary_path:
                raise FileNotFoundError(
                    f"Could not find {name} executable after extracting {local_path}"
                )

            self._prepend_to_path(binary_path)
            return binary_path

        if local_path.is_file():
            self._prepend_to_path(local_path)

        return local_path

    def fetch_binary(self, name: str, prompt_user: bool = True) -> Path:
        dep_info = self.deps.get(name, {}).get(PLATFORM, {})

        # System-wide first
        sys_path = self._find_binary_on_path(name, dep_info)
        if sys_path:
            self.logger.debug(f"{name} found system-wide at {sys_path}")
            return sys_path

        local_binary = self._find_local_binary(name, dep_info)
        if local_binary:
            self.logger.debug(f"{name} found in {self.install_folder}")
            return local_binary

        url = self._resolve_download_url(name, dep_info)

        local_path = self.install_folder / Path(url).name if url else None

        # Local archive/file by resolved download URL
        local_binary = self._resolve_local_binary(name, dep_info, local_path)
        if local_binary:
            self.logger.debug(f"{name} found in {self.install_folder}")
            return local_binary

        if not prompt_user:
            if url:
                return self._download_binary(name, dep_info, url)
            raise FileNotFoundError(f"Could not locate {name} on PATH")

        package_error = None
        portable_error = None

        if url:
            if self._confirm_install(
                f"{name} was not found on PATH. Install a portable copy into {self.install_folder} for this runtime?"
            ):
                try:
                    return self._download_binary(name, dep_info, url)
                except Exception as exc:
                    portable_error = exc
                    self.logger.warning(f"Portable install failed for {name}: {exc}")

        pkg_name = dep_info.get("package")
        if pkg_name and self._confirm_install(
            f"{name} is still unavailable. Install it with the system package manager?"
        ):
            if self._install_with_package_manager(name):
                sys_path_after = self._find_binary_on_path(name, dep_info)
                if sys_path_after:
                    return sys_path_after
                package_error = FileNotFoundError(
                    f"{name} was installed but is not available on PATH in the current runtime"
                )
            else:
                package_error = RuntimeError(
                    f"Package manager installation failed for {name}"
                )

        if portable_error:
            raise portable_error
        if package_error:
            raise package_error

        install_hint = (
            f"{name} was not found on PATH. Re-run and accept the portable install prompt."
            if url
            else f"{name} was not found on PATH. Re-run and accept the package manager install prompt."
        )
        raise FileNotFoundError(install_hint)

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
    # TODO: check if aniskip is selected in future for IINA to fallback to mpv for functionality if issue #200 is fixed

    if PLATFORM == "Darwin" and use_iina:
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
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "xvfb"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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
        _log.debug("Installing patchright chromium (this may take a moment)...")
        subprocess.run(
            [sys.executable, "-m", "patchright", "install", "chromium"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log.debug("patchright chromium is ready")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _log.warning(f"patchright chromium install failed: {e}")


if __name__ == "__main__":
    print(get_player_path())
    print(get_syncplay_path())
