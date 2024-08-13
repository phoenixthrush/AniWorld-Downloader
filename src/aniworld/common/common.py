import platform
import os
import shutil
import sys
from typing import Optional

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
