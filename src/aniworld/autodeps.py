import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import zipfile
from contextlib import closing
from pathlib import Path

PLATFORM = platform.system()

try:
    from .common import fetch_github_asset_urls
    from .config import ANIWORLD_CONFIG_DIR, GLOBAL_SESSION
    from .env import resolve_env_directory
    from .logger import get_logger

except ImportError:
    from aniworld.common import fetch_github_asset_urls
    from aniworld.config import ANIWORLD_CONFIG_DIR, GLOBAL_SESSION
    from aniworld.env import resolve_env_directory
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
def get_syncplay_release_url() -> list[str]:
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
# Auto-install kill switch
# -----------------------------
def auto_install_disabled() -> bool:
    """True when ANIWORLD_NO_AUTO_INSTALL=1.

    Blocks every unattended download/install the app would otherwise do on its
    own: the portable binaries, the system package manager (which shells out to
    sudo), Xvfb and the patchright Chromium. Anything already installed is
    still used normally.
    """
    return os.getenv("ANIWORLD_NO_AUTO_INSTALL", "0").strip() == "1"


# -----------------------------
# Dependency Manager
# -----------------------------
class DependencyManager:
    """Manage binaries with system package manager or direct download."""

    def __init__(self, install_folder=None):
        self.deps = deps
        configured_install_folder = install_folder or ANIWORLD_CONFIG_DIR
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
    ) -> Path | None:
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

    def _find_binary_on_path(self, name: str, dep_info: dict) -> Path | None:
        binary_names = [name, *(dep_info.get("binary_names") or [])]

        for binary_name in dict.fromkeys(binary_names):
            sys_path = shutil.which(binary_name)
            if sys_path:
                return Path(sys_path)

        return None

    def _find_local_binary(self, name: str, dep_info: dict) -> Path | None:
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
        if auto_install_disabled():
            self.logger.debug(f"ANIWORLD_NO_AUTO_INSTALL=1 — skipping: {message}")
            return False

        if not sys.stdin or not sys.stdin.isatty():
            return False

        prompt = "[Y/n]" if default else "[y/N]"
        reply = input(f"{message} {prompt} ").strip().lower()
        if not reply:
            return default
        return reply in {"y", "yes"}

    def _resolve_download_url(self, name: str, dep_info: dict) -> str | None:
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
            f.writelines(resp.iter_content(chunk_size=8192))

        if PLATFORM != "Windows":
            local_path.chmod(0o755)

        self.logger.debug(f"{name} downloaded to {local_path}")
        resolved_binary = self._resolve_local_binary(name, dep_info, local_path)
        return resolved_binary or local_path

    def _resolve_local_binary(self, name: str, dep_info: dict, local_path: Path | None):
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

        url = (
            dep_info.get("url")
            if auto_install_disabled()
            else self._resolve_download_url(name, dep_info)
        )

        local_path = self.install_folder / Path(url).name if url else None

        # Local archive/file by resolved download URL
        local_binary = self._resolve_local_binary(name, dep_info, local_path)
        if local_binary:
            self.logger.debug(f"{name} found in {self.install_folder}")
            return local_binary

        if auto_install_disabled():
            raise FileNotFoundError(
                f"{name} was not found locally and automatic installation is disabled "
                "(ANIWORLD_NO_AUTO_INSTALL=1). Install it manually and add it to PATH "
                f"or {self.install_folder}."
            )

        if not prompt_user:
            if url:
                return self._download_binary(name, dep_info, url)
            raise FileNotFoundError(f"Could not locate {name} on PATH")

        package_error = None
        portable_error = None

        if url and self._confirm_install(
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
        if auto_install_disabled():
            self.logger.debug(
                f"ANIWORLD_NO_AUTO_INSTALL=1 — not installing {name} via package manager"
            )
            return False

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
def get_player_path(*, use_iina=None) -> Path:
    manager = DependencyManager()
    if use_iina is None:
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
        if auto_install_disabled():
            _log.warning(
                "Xvfb not found and ANIWORLD_NO_AUTO_INSTALL=1 — install it yourself "
                "(e.g. 'sudo apt install xvfb') or set DISPLAY to an existing X server."
            )
            return
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


def _default_playwright_browsers_path() -> Path:
    """Return Playwright's platform-specific browser cache directory."""
    if PLATFORM == "Windows":
        cache_dir = resolve_env_directory(
            "LOCALAPPDATA", Path.home() / "AppData" / "Local"
        )
        return cache_dir / "ms-playwright"

    if PLATFORM == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"

    cache_dir = resolve_env_directory("XDG_CACHE_HOME", Path.home() / ".cache")
    return cache_dir / "ms-playwright"


def ensure_patchright_chromium():
    """Install the patchright Chromium browser if not already present."""
    _log = get_logger(__name__)
    if auto_install_disabled():
        _log.debug("ANIWORLD_NO_AUTO_INSTALL=1 — skipping chromium setup")
        return

    try:
        import patchright  # noqa: F401
    except ImportError:
        _log.debug("patchright not installed, skipping chromium check")
        return

    try:
        from patchright._impl._driver import compute_driver_executable, get_driver_env
        from patchright.sync_api import sync_playwright

        os.environ.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH",
            _default_playwright_browsers_path().resolve().as_posix(),
        )

        driver_executable, driver_cli = compute_driver_executable()
        driver_path = Path(driver_executable).resolve()
        os.environ.setdefault("PLAYWRIGHT_NODEJS_PATH", driver_path.as_posix())

        if PLATFORM != "Windows" and not os.access(driver_path, os.X_OK):
            driver_path.chmod(driver_path.stat().st_mode | 0o111)

        with sync_playwright() as runtime:
            if Path(runtime.chromium.executable_path).is_file():
                return

        _log.debug("Installing patchright chromium (this may take a moment)...")
        subprocess.run(
            [
                driver_path.as_posix(),
                driver_cli,
                "install",
                "chromium",
                "--no-shell",
            ],
            check=True,
            env=get_driver_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log.debug("patchright chromium is ready")
    except (subprocess.CalledProcessError, OSError) as e:
        _log.warning(f"patchright chromium install failed: {e}")


_CHROMIUM_DEPS_LOCK = threading.Lock()


class ChromiumDependencyError(RuntimeError):
    """Chromium cannot load one of its Linux runtime libraries."""


def _missing_chromium_library(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "--version"],
            env={**os.environ, "LC_ALL": "C"},
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None  # Let the normal browser launch diagnose other failures.
    if result.returncode == 0:
        return None
    missing = re.search(
        r"error while loading shared libraries: ([^:\s]+):", result.stderr
    )
    return missing[1] if missing else None


def _supports_chromium_dependency_install() -> bool:
    if platform.machine() not in ("x86_64", "aarch64") or not shutil.which("apt-get"):
        return False
    try:
        distro = platform.freedesktop_os_release()
    except OSError:
        return False
    # Patchright provides native Chromium package lists for these Linux releases.
    versions = {"debian": ("12", "13"), "ubuntu": ("22.04", "24.04", "26.04")}
    return distro.get("VERSION_ID") in versions.get(distro.get("ID"), ())


def ensure_chromium_system_dependencies(executable: str) -> None:
    """Diagnose missing Linux libraries and repair them where apt is supported."""
    if PLATFORM != "Linux":
        return

    with _CHROMIUM_DEPS_LOCK:
        library = _missing_chromium_library(executable)
        if library is None:
            return

        if not _supports_chromium_dependency_install():
            raise ChromiumDependencyError(
                f"Chromium cannot load {library}. "
                "Install the missing library with your distribution's package manager."
            )

        hint = "Run 'python -m patchright install-deps chromium', then try again."
        if auto_install_disabled() or (
            os.geteuid() != 0 and not (sys.stdin and sys.stdin.isatty())
        ):
            raise ChromiumDependencyError(f"Chromium cannot load {library}. {hint}")

        from patchright._impl._driver import compute_driver_executable, get_driver_env

        get_logger(__name__).warning(
            "Chromium cannot load %s. Installing its Linux system dependencies.",
            library,
        )
        try:
            driver, cli = compute_driver_executable()
            subprocess.run(
                [driver, cli, "install-deps", "chromium"],
                check=True,
                env=get_driver_env(),
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ChromiumDependencyError(
                f"Chromium cannot load {library}. Dependency setup failed. {hint}"
            ) from exc

        library = _missing_chromium_library(executable)
        if library is not None:
            raise ChromiumDependencyError(
                f"Chromium still cannot load {library}. {hint}"
            )


_UBLOCK_BUNDLED_DIR = Path(__file__).with_name("ublock-lite")


def _ublock_installed(directory: Path) -> bool:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and manifest.get("manifest_version") == 3


def install_ublock_lite() -> str | None:
    """Prepare uBlock Origin Lite in the config directory once."""
    _log = get_logger(__name__)
    target = Path(ANIWORLD_CONFIG_DIR).expanduser().resolve() / "ublock-lite"
    for installed in (_UBLOCK_BUNDLED_DIR, target):
        if _ublock_installed(installed):
            return str(installed)
    if auto_install_disabled():
        _log.debug("ANIWORLD_NO_AUTO_INSTALL=1 — skipping uBlock Origin Lite setup")
        return None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Serialize first-time setup across processes as well as browser threads.
        with closing(
            sqlite3.connect(target.parent / ".ublock-lite.lock", timeout=120)
        ) as lock:
            lock.execute("BEGIN IMMEDIATE")
            if _ublock_installed(target):
                return str(target)

            urls = fetch_github_asset_urls(
                "uBlockOrigin/uBOL-home", r"uBOLite_[\d.]+\.chromium\.zip$"
            )
            if not urls:
                raise ValueError(
                    "the latest uBlockOrigin/uBOL-home release has no Chromium ZIP "
                    "(uBOLite_*.chromium.zip)"
                )
            url = urls[0]
            with tempfile.TemporaryDirectory(
                prefix="ublock-lite.", dir=target.parent
            ) as temp:
                staging = Path(temp)
                archive = staging / "ublock-lite.zip"
                print("[DOWNLOADING] uBlock Origin Lite", flush=True)
                with GLOBAL_SESSION.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    with archive.open("wb") as file:
                        file.writelines(response.iter_content(chunk_size=8192))
                print("[EXTRACTING] uBlock Origin Lite", flush=True)
                extension = staging / "extension"
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(extension)
                if not _ublock_installed(extension):
                    raise ValueError(
                        "the archive has no valid Chromium extension manifest"
                    )
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.exists():
                    shutil.rmtree(target)
                extension.rename(target)
        return str(target)
    except Exception as e:
        if _ublock_installed(target):
            return str(target)
        _log.warning(f"uBlock Origin Lite setup failed: {e}")
        return None


def ensure_ublock_lite() -> str | None:
    """Use or prepare uBlock Origin Lite when ANIWORLD_UBLOCK=1."""
    if os.getenv("ANIWORLD_UBLOCK", "0").strip() == "1":
        return install_ublock_lite()
    return None


def launch_ublock_context(chromium, extension, **options):
    """Return a temporary-profile context and its closer, or None on launch failure."""
    from patchright.sync_api import Error

    options.setdefault("timeout", 30_000)
    args = [
        *options.pop("args", ()),
        f"--disable-extensions-except={extension}",
        f"--load-extension={extension}",
    ]
    user_data_dir = None
    try:
        user_data_dir = tempfile.mkdtemp(prefix="aniworld-chromium-")
        context = chromium.launch_persistent_context(
            user_data_dir, args=args, **options
        )
    except Exception as exc:
        if user_data_dir is not None:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        if not isinstance(exc, (Error, OSError)):
            raise
        get_logger(__name__).warning(
            "Starting Chromium without uBlock Origin Lite: %s", exc
        )
        return None

    def close():
        try:
            context.close()
        finally:
            shutil.rmtree(user_data_dir, ignore_errors=True)

    return context, close


if __name__ == "__main__":
    print(get_player_path())
    print(get_syncplay_path())
