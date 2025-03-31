import json
import logging
import platform
import shutil
import subprocess
import sys
import os
import re

import requests

# extremly unreliable lol


def check_avx2_support() -> bool:
    if platform.system() != "Windows":
        logging.debug("AVX2 check is only supported on Windows.")
        return False

    try:
        if shutil.which("wmic"):
            cpu_info = subprocess.run(
                ['wmic', 'cpu', 'get', 'Caption,InstructionSet'],
                capture_output=True,
                text=True,
                check=False
            )
            if 'avx2' in cpu_info.stdout.lower():
                return True
            logging.debug("AVX2 not found in CPU info.")
    except subprocess.SubprocessError as e:
        logging.error("Error checking AVX2 support: %s", e)

    try:
        registry_info = subprocess.run(
            [
                'reg', 'query',
                'HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0',
                '/v', 'FeatureSet'
            ],
            capture_output=True,
            text=True,
            check=False
        )
        if 'avx2' in registry_info.stdout.lower():
            return True
    except subprocess.SubprocessError as e:
        logging.error("Error checking AVX2 support via registry: %s", e)

    return False


def get_github_release(repo: str) -> dict:
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"

    try:
        response = requests.get(api_url, timeout=15)
        response.raise_for_status()
        release_data = response.json()
        assets = release_data.get('assets', [])
        return {asset['name']: asset['browser_download_url'] for asset in assets}
    except (json.JSONDecodeError, requests.RequestException) as e:
        logging.error("Failed to fetch release data from GitHub: %s", e)
    return {}


def download_mpv(dep_path: str = None, appdata_path: str = None):
    if sys.platform != 'win32':
        return

    appdata_path = appdata_path or os.path.join(
        os.environ['USERPROFILE'], 'AppData', 'Roaming', 'aniworld'
    )
    dep_path = dep_path or os.path.join(appdata_path, "mpv")
    os.makedirs(dep_path, exist_ok=True)

    executable_path = os.path.join(dep_path, 'mpv.exe')
    zip_path = os.path.join(dep_path, 'mpv.7z')
    zip_tool = os.path.join(appdata_path, "7z", "7zr.exe")
    os.makedirs(os.path.dirname(zip_tool), exist_ok=True)

    if os.path.exists(executable_path):
        return

    direct_links = get_github_release("shinchiro/mpv-winbuild-cmake")
    avx2_supported = check_avx2_support()
    pattern = (
        r'mpv-x86_64-v3-\d{8}-git-[a-f0-9]{7}\.7z'
        if avx2_supported
        else r'mpv-x86_64-\d{8}-git-[a-f0-9]{7}\.7z'
    )
    logging.debug("Downloading MPV using pattern: %s", pattern)
    direct_link = next(
        (link for name, link in direct_links.items() if re.match(pattern, name)),
        None
    )

    if not direct_link:
        logging.error(
            "No suitable MPV download link found. Please download manually.")
        return

    if not os.path.exists(zip_tool):
        print("Downloading 7z...")
        r = requests.get('https://7-zip.org/a/7zr.exe',
                         allow_redirects=True, timeout=15)
        with open(zip_tool, 'wb') as f:
            f.write(r.content)

    if not os.path.exists(zip_path):
        logging.debug("Downloading MPV from %s to %s", direct_link, zip_path)
        try:
            print(
                f"Downloading MPV ({'without' if not avx2_supported else 'with'} AVX2)...")
            print(direct_link)
            with requests.get(direct_link, allow_redirects=True, timeout=15) as r:
                r.raise_for_status()
                with open(zip_path, 'wb') as f:
                    f.write(r.content)
        except requests.RequestException as e:
            logging.error("Failed to download MPV: %s", e)
            return

    logging.debug("Extracting MPV to %s", dep_path)
    try:
        subprocess.run(
            [zip_tool, "x", zip_path],
            check=True,
            cwd=dep_path,
            stdout=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError,
            subprocess.SubprocessError) as e:
        logging.error("Failed to extract files: %s", e)

    # os.remove(zip_path)
    logging.debug("Download and extraction complete.")

    logging.debug("Adding MPV path to environment: %s", dep_path)
    os.environ["PATH"] += os.pathsep + dep_path
