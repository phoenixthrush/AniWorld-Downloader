import glob
import platform
import os
import shutil
import sys
import shlex
import subprocess
from typing import List, Optional

import requests


def check_dependencies(dependencies: list) -> None:
    """
    Check if dependencies are available in PATH and handle platform-specific cases.

    Args:
        dependencies (list): List of dependency names.

    Returns:
        None

    Exits:
        Exits with error if any dependency is missing.
    """
    resolved_dependencies = []

    for dep in dependencies:
        if dep == "syncplay":
            if platform.system() == "nt":
                resolved_dependencies.append("SyncplayConsole")
            else:
                resolved_dependencies.append("syncplay")
        else:
            resolved_dependencies.append(dep)

    missing = [dep for dep in resolved_dependencies if shutil.which(dep) is None]

    if missing:
        print(f"Missing dependencies: {', '.join(missing)} in path. Please install and try again.")
        sys.exit(1)


def fetch_url_content(url: str, proxy: Optional[str] = None, check: bool = True) -> Optional[bytes]:
    """
    Fetch content from a URL with optional proxy.

    Args:
        url (str): The URL to fetch.
        proxy (str, optional): Proxy URL (supports SOCKS and HTTP).
        check (bool, optional): If True, exits on failure. If False, returns None on failure.

    Returns:
        Optional[bytes]: Content of the URL or None if an error occurs and check is False.

    Exits:
        Exits with error if check is True and the request fails.
    """
    headers = {
        'User-Agent': (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/58.0.3029.110 Safari/537.3"
        )
    }

    proxies = {}
    if proxy:
        if proxy.startswith('socks'):
            proxies = {
                'http': proxy,
                'https': proxy
            }
        else:
            proxies = {
                'http': f'http://{proxy}',
                'https': f'https://{proxy}'
            }

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        response.raise_for_status()

        if "Deine Anfrage wurde als Spam erkannt." in response.text:
            print("Your IP address is blacklisted. Please use a VPN or try again later.")
            sys.exit(1)

        return response.content
    except requests.exceptions.RequestException as error:
        if check:
            print(f"Request to {url} failed: {error}")
            sys.exit(1)
        return None


def clear_screen() -> None:
    """
    Clear the terminal screen based on the operating system.
    """
    if platform.system() == "nt":
        os.system("cls")
    else:
        os.system("clear")


def clean_up_leftovers(directory: str) -> None:
    """
    Removes leftover files in the specified directory that match certain patterns.
    Also removes the directory if it becomes empty after cleanup.

    This method searches for files in the given directory that match the following patterns:
    - '*.part'
    - '*.ytdl'
    - '*.part-Frag*'

    Args:
        directory (str): The directory where leftover files are to be removed.

    Returns:
        None: This method does not return any value.
    """
    patterns: List[str] = ['*.part', '*.ytdl', '*.part-Frag*']

    leftover_files: List[str] = []
    for pattern in patterns:
        leftover_files.extend(glob.glob(os.path.join(directory, pattern)))

    for file_path in leftover_files:
        try:
            os.remove(file_path)
            print(f"Removed leftover file: {file_path}")
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except PermissionError:
            print(f"Permission denied when trying to remove file: {file_path}")
        except OSError as e:
            print(f"OS error occurred while removing file {file_path}: {e}")

    if not os.listdir(directory):
        try:
            os.rmdir(directory)
            print(f"Removed empty directory: {directory}")
        except FileNotFoundError:
            print(f"Directory not found: {directory}")
        except PermissionError:
            print(f"Permission denied when trying to remove directory: {directory}")
        except OSError as e:
            print(f"OS error occurred while removing directory {directory}: {e}")


def setup_aniskip() -> None:
    """
    Copy 'skip.lua' to the correct MPV scripts directory based on the OS.
    """
    script_directory = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(script_directory, 'aniskip', 'skip.lua')

    if os.name == 'nt':
        destination_path = os.path.join(
            os.environ['APPDATA'], 'mpv', 'scripts', 'skip.lua'
        )
    else:
        destination_path = os.path.expanduser(
            '~/.config/mpv/scripts/skip.lua'
        )

    if not os.path.exists(destination_path):
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy(source_path, destination_path)


def execute_command(command: List[str], only_command: bool) -> None:
    """
    Execute a command or print it as a string based on the 'only_command' flag.

    Args:
        command: List of command arguments.
        only_command: If True, print the command; otherwise, execute it.
    """
    if only_command:
        print(' '.join(shlex.quote(arg) for arg in command))
    else:
        subprocess.run(command, check=True)
