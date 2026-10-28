import shutil
import sys
from pathlib import Path

try:
    from ..common import get_latest_github_release, unzip
    from ..config import ANIWORLD_CONFIG_DIR, GLOBAL_SESSION, MPV_CONFIG_DIR, logger
except ImportError:
    from aniworld.common import get_latest_github_release, unzip
    from aniworld.config import (
        ANIWORLD_CONFIG_DIR,
        GLOBAL_SESSION,
        MPV_CONFIG_DIR,
        logger,
    )


def get_anime4k_folder_names():
    """Return platform-specific Anime4K folder names."""
    platform_folders = {
        "win": {"low": "GLSL_Windows_Low-end", "high": "GLSL_Windows_High-end"},
        "linux": {"low": "GLSL_Mac_Linux_Low-end", "high": "GLSL_Mac_Linux_High-end"},
        "darwin": {"low": "GLSL_Mac_Linux_Low-end", "high": "GLSL_Mac_Linux_High-end"},
    }

    for key, folders in platform_folders.items():
        if sys.platform.startswith(key):
            return folders

    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def get_anime4k_urls():
    """Return platform-specific Anime4K GLSL URLs."""
    repo = "Tama47/Anime4K"
    release = get_latest_github_release(repo)

    folder_names = get_anime4k_folder_names()

    base = f"https://github.com/{repo}/releases/download/{release}/"
    return {
        "low": base + folder_names["low"] + ".zip",
        "high": base + folder_names["high"] + ".zip",
    }


def download_anime4k(target_dir=None, mode="high"):
    """Download Anime4K GLSL assets only if not already extracted."""
    target_dir = Path(target_dir or ANIWORLD_CONFIG_DIR).expanduser() / "Anime4K"
    target_dir.mkdir(parents=True, exist_ok=True)

    if mode == "remove":
        if target_dir.exists():
            shutil.rmtree(target_dir)
            logger.debug(f"[REMOVED] Anime4K directory: {target_dir}")
        return []

    urls = get_anime4k_urls()
    if mode not in urls:
        raise ValueError(f"Invalid mode '{mode}'. Use 'high', 'low', or 'remove'.")

    downloaded_files = []
    url = urls[mode]
    filename = Path(url).name
    extracted_dir = target_dir / Path(filename).stem

    if extracted_dir.exists():
        logger.debug(f"{extracted_dir} exists, skipping download of {filename}")
        downloaded_files.append(target_dir / filename)
    else:
        filepath = target_dir / filename
        logger.debug(f"Downloading {filename}...")
        with GLOBAL_SESSION.get(url, stream=True) as response:
            response.raise_for_status()
            with open(filepath, "wb") as f:
                shutil.copyfileobj(response.raw, f)
        logger.debug(f"Downloaded {filename} to {target_dir}")
        downloaded_files.append(filepath)

    return downloaded_files


def extract_anime4k(files, target_dir=None):
    """Extract downloaded zip files and clean up."""
    target_dir = Path(target_dir or ANIWORLD_CONFIG_DIR).expanduser() / "Anime4K"
    extracted_dirs = []

    for filepath in files:
        filepath = Path(filepath).expanduser()
        extracted_dir = target_dir / filepath.stem
        if extracted_dir.exists():
            logger.debug(f"{extracted_dir} exists, skipping extraction.")
        else:
            unzip(filepath, extracted_dir)
            macosx_dir = extracted_dir / "__MACOSX"
            if macosx_dir.exists():
                shutil.rmtree(macosx_dir)
            logger.debug(f"Extracted {filepath.name} -> {extracted_dir}")
        filepath.unlink(missing_ok=True)
        extracted_dirs.append(extracted_dir)

    return extracted_dirs


def detect_current_mode():
    """Detect the currently installed Anime4K mode from input.conf."""
    input_conf = MPV_CONFIG_DIR / "input.conf"
    if not input_conf.exists():
        return None

    with open(input_conf, "r", encoding="utf-8") as f:
        content = f.read()

    if "# Optimized shaders for lower-end GPU:" in content:
        return "low"
    if "# Optimized shaders for higher-end GPU:" in content:
        return "high"
    return None


def copy_with_markers(src_file, dst_file):
    """Copy a config file and wrap it with Anime4K markers."""
    src_file = Path(src_file).expanduser()
    dst_file = Path(dst_file).expanduser()
    with open(src_file, "r", encoding="utf-8") as f:
        content = f.read()

    content = f"# BEGIN Anime4K CONFIG\n{content}\n# END Anime4K CONFIG\n"

    with open(dst_file, "w", encoding="utf-8") as f:
        f.write(content)

    logger.debug(f"Copied {src_file} -> {dst_file} with markers")


def setup_anime4k(mode="low"):
    """Copy shaders and config files to MPV directory."""
    mpv_shaders_dir = MPV_CONFIG_DIR / "shaders"
    mpv_shaders_dir.mkdir(parents=True, exist_ok=True)

    # Get the correct folder names for this platform
    mode_folders = get_anime4k_folder_names()

    if mode not in mode_folders:
        logger.error(f"Unknown mode: {mode}. Valid modes: {list(mode_folders.keys())}")
        return

    source_dir = Path(ANIWORLD_CONFIG_DIR) / "Anime4K" / mode_folders[mode]
    if not source_dir.exists():
        logger.warning(f"{source_dir} does not exist. Nothing to set up.")
        return

    # Use the specific mode directory instead of iterating through all folders
    folder = source_dir

    # Copy shaders
    shaders_dir = folder / "shaders"
    if shaders_dir.exists():
        for shader in shaders_dir.iterdir():
            dst_file = mpv_shaders_dir / shader.name
            if not dst_file.exists():
                shutil.copy(shader, dst_file)
                logger.debug(f"Copied shader {shader} -> {dst_file}")

    # Copy configs with markers
    for conf_name in ("mpv.conf", "input.conf"):
        src_conf = folder / conf_name
        dst_conf = MPV_CONFIG_DIR / conf_name
        if src_conf.exists() and not dst_conf.exists():
            copy_with_markers(src_conf, dst_conf)


def remove_anime4k_lines(file_path):
    """Remove Anime4K block from a config file."""
    file_path = Path(file_path).expanduser()
    if not file_path.exists():
        return

    start_marker = "# BEGIN Anime4K CONFIG"
    end_marker = "# END Anime4K CONFIG"

    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    final_lines = []
    in_block = False
    for line in lines:
        if line.strip() == start_marker:
            in_block = True
            continue
        if line.strip() == end_marker:
            in_block = False
            continue
        if not in_block:
            final_lines.append(line)

    if not final_lines:
        file_path.unlink()
        logger.debug(f"[REMOVED] {file_path} (empty after removing Anime4K block)")
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(final_lines)
        logger.debug(f"[REMOVED] Anime4K lines from {file_path}")


def anime4k(mode="high"):
    """Main entry point for Anime4K setup and removal with mode detection."""
    mpv_shaders_dir = MPV_CONFIG_DIR / "shaders"

    if mode not in ("high", "low", "remove"):
        raise ValueError(f"Invalid mode '{mode}'. Use 'high', 'low', or 'remove'.")

    # Remove mode
    if mode == "remove":
        if mpv_shaders_dir.exists():
            for shader in mpv_shaders_dir.iterdir():
                if shader.is_file() and shader.name.startswith("Anime4K_"):
                    shader.unlink()
                    logger.debug(f"[REMOVED] {shader}")
            if not any(mpv_shaders_dir.iterdir()):
                mpv_shaders_dir.rmdir()
                logger.debug(f"[REMOVED] Empty shaders folder: {mpv_shaders_dir}")

        for conf_name in ("mpv.conf", "input.conf"):
            remove_anime4k_lines(MPV_CONFIG_DIR / conf_name)

        logger.debug("Anime4K assets, shaders, and configs removed successfully.")
        return

    # Detect current installed mode
    current_mode = detect_current_mode()
    if current_mode == mode:
        logger.debug(f"Anime4K already installed in '{mode}' mode. Skipping setup.")
        return
    elif current_mode is not None and current_mode != mode:
        logger.debug(f"Switching Anime4K from '{current_mode}' to '{mode}' mode...")
        # Remove previous mode first
        anime4k(mode="remove")

    # Normal setup
    downloaded = download_anime4k(mode=mode)
    extract_anime4k(downloaded)
    setup_anime4k(mode=mode)
    logger.debug(f"Anime4K setup complete in '{mode}' mode.")


if __name__ == "__main__":
    anime4k(mode="high")  # options: "high", "low", "remove"
