import re
import subprocess
import sys
from pathlib import Path

try:
    from ..config import GLOBAL_SESSION
except ImportError:
    from aniworld.config import GLOBAL_SESSION


GITHUB_BASE_URL = "https://github.com"


def _extract_github_release_tag_from_url(url):
    match = re.search(r"/releases/tag/([^/?#]+)", url)
    return match.group(1) if match else None


def _extract_github_asset_urls_from_html(html, asset_patterns):
    href_pattern = re.compile(r'href="([^"]+/releases/download/[^"]+)"', re.IGNORECASE)
    matched_urls = []

    for pattern_str in asset_patterns:
        pattern = re.compile(pattern_str, re.IGNORECASE)
        for match in href_pattern.finditer(html):
            url = match.group(1)
            full_url = (
                f"{GITHUB_BASE_URL}{url}" if url.startswith("/") else url
            )
            if pattern.search(full_url) and full_url not in matched_urls:
                matched_urls.append(full_url)

    return matched_urls


def get_latest_github_release(repo):
    """
    Fetch the latest release tag of a GitHub repository.

    Args:
        repo: GitHub repo in "owner/repo" format, e.g. "shinchiro/mpv-winbuild-cmake"

    Returns:
        The tag name of the latest release
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        resp = GLOBAL_SESSION.get(api_url)
        resp.raise_for_status()
        release_data = resp.json()
        return release_data.get("tag_name")
    except Exception:
        html_url = f"{GITHUB_BASE_URL}/{repo}/releases/latest"
        resp = GLOBAL_SESSION.get(html_url, allow_redirects=True)
        resp.raise_for_status()
        release_tag = _extract_github_release_tag_from_url(str(resp.url))
        if not release_tag:
            raise RuntimeError(f"Could not determine latest release for {repo}")
        return release_tag


def fetch_github_asset_urls(repo, asset_patterns, release="latest"):
    """
    Fetch all download URLs of GitHub release assets matching one or more regex patterns.

    Args:
        repo: GitHub repo in "owner/repo" format, e.g. "shinchiro/mpv-winbuild-cmake"
        asset_patterns: Regex pattern(s) to match asset file names
        release: Release tag or "latest" (default)

    Returns:
        List of URLs matching any of the patterns (empty list if none found)
    """
    if isinstance(asset_patterns, str):
        asset_patterns = [asset_patterns]

    if release == "latest":
        release = get_latest_github_release(repo)

    api_url = f"https://api.github.com/repos/{repo}/releases/tags/{release}"
    try:
        resp = GLOBAL_SESSION.get(api_url)
        resp.raise_for_status()
        assets = resp.json().get("assets", [])

        matched_urls = []

        for pattern_str in asset_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            for asset in assets:
                url = asset.get("browser_download_url")
                if url and pattern.search(url):
                    matched_urls.append(url)

        return matched_urls
    except Exception:
        html_url = f"{GITHUB_BASE_URL}/{repo}/releases/expanded_assets/{release}"
        resp = GLOBAL_SESSION.get(html_url)
        resp.raise_for_status()
        return _extract_github_asset_urls_from_html(resp.text, asset_patterns)


def unzip(file_path, target_dir):
    file_path = Path(file_path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if file_path.suffix.lower() == ".zip":
        if sys.platform.startswith("win"):
            # TODO: implement
            pass
        else:
            # Use system unzip on macOS/Linux
            print(f"Extracting ZIP: {file_path} -> {target_dir}")
            subprocess.run(
                ["unzip", "-o", str(file_path), "-d", str(target_dir)], check=True
            )
    elif file_path.suffix.lower() == ".7z":
        # use 7z
        if sys.platform.startswith("win"):
            # TODO: implement
            pass
        else:
            # Use system 7z on macOS/Linux
            print(f"Extracting 7z: {file_path} -> {target_dir}")
            subprocess.run(
                ["7z", "x", str(file_path), f"-o{str(target_dir)}"], check=True
            )
    else:
        raise ValueError(f"Unsupported archive format: {file_path}")
