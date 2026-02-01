import re
import random
import time
import logging
from typing import Optional
from urllib.parse import urljoin

import requests

from ...config import RANDOM_USER_AGENT, DEFAULT_REQUEST_TIMEOUT, REQUEST_VERIFY

# Constants
DOODSTREAM_BASE_URL = "https://dood.li"
RANDOM_STRING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
PASS_MD5_PATTERN = r"\$\.get\('([^']*\/pass_md5\/[^']*)'"
TOKEN_PATTERN = r"token=([a-zA-Z0-9]+)"


def _get_headers() -> dict:
    """Get request headers for Doodstream."""
    return {"User-Agent": RANDOM_USER_AGENT, "Referer": f"{DOODSTREAM_BASE_URL}/"}


def _make_request(url: str, headers: dict) -> requests.Response:
    """Make HTTP request with error handling."""
    try:
        response = requests.get(
            url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT, verify=REQUEST_VERIFY
        )
        response.raise_for_status()
        return response
    except requests.RequestException as err:
        logging.error(f"Request failed for {url}: {err}")
        raise


def _extract_data(pattern: str, content: str) -> Optional[str]:
    """Extract data using regex pattern."""
    match = re.search(pattern, content)
    return match.group(1) if match else None


def _generate_random_string(length: int = 10) -> str:
    """Generate random alphanumeric string."""
    return "".join(random.choice(RANDOM_STRING_CHARS) for _ in range(length))


def _extract_pass_md5_url(content: str, embed_url: str) -> str:
    """Extract pass_md5 URL from page content."""
    pass_md5_url = _extract_data(PASS_MD5_PATTERN, content)
    if not pass_md5_url:
        raise ValueError(f"pass_md5 URL not found in {embed_url}")

    # Ensure URL is properly formed
    if not pass_md5_url.startswith("http"):
        pass_md5_url = urljoin(DOODSTREAM_BASE_URL, pass_md5_url)

    logging.debug(f"Extracted pass_md5 URL: {pass_md5_url}")
    return pass_md5_url


def _extract_token(content: str, embed_url: str) -> str:
    """Extract token from page content."""
    token = _extract_data(TOKEN_PATTERN, content)
    if not token:
        raise ValueError(f"Token not found in {embed_url}")

    logging.debug(f"Extracted token: {token}")
    return token


def _get_video_base_url(pass_md5_url: str, headers: dict) -> str:
    """Get video base URL from pass_md5 endpoint."""
    try:
        md5_response = _make_request(pass_md5_url, headers)
        video_base_url = md5_response.text.strip()

        if not video_base_url:
            raise ValueError("Empty video base URL received")

        logging.debug(f"Retrieved video base URL: {video_base_url}")
        return video_base_url

    except Exception as err:
        logging.error(f"Failed to get video base URL from {pass_md5_url}: {err}")
        raise


def _build_direct_link(video_base_url: str, token: str) -> str:
    """Build the final direct link."""
    random_string = _generate_random_string(10)
    expiry = int(time.time())

    direct_link = f"{video_base_url}{random_string}?token={token}&expiry={expiry}"
    logging.debug(f"Built direct link: {direct_link}")
    return direct_link


def get_direct_link_from_doodstream(embeded_doodstream_link: str) -> str:
    """
    Extract direct download link from Doodstream embed URL.

    Args:
        embeded_doodstream_link: Doodstream embed URL

    Returns:
        Direct download link

    Raises:
        ValueError: If required data cannot be extracted
        requests.RequestException: If HTTP requests fail
    """
    if not embeded_doodstream_link:
        raise ValueError("Embed URL cannot be empty")

    logging.info(f"Extracting direct link from Doodstream: {embeded_doodstream_link}")

    try:
        headers = _get_headers()

        # Get initial page content
        logging.debug("Fetching embed page content...")
        response = _make_request(embeded_doodstream_link, headers)

        # Extract pass_md5 URL and token
        pass_md5_url = _extract_pass_md5_url(response.text, embeded_doodstream_link)
        token = _extract_token(response.text, embeded_doodstream_link)

        # Get video base URL
        video_base_url = _get_video_base_url(pass_md5_url, headers)

        # Build final direct link
        direct_link = _build_direct_link(video_base_url, token)

        logging.info("Successfully extracted Doodstream direct link")
        return direct_link

    except Exception as err:
        logging.error(f"Failed to extract direct link from Doodstream: {err}")
        raise


if __name__ == "__main__":
    # Setup basic logging for standalone execution
    logging.basicConfig(level=logging.DEBUG)

    try:
        link = input("Enter Doodstream Link: ").strip()
        if not link:
            print("Error: No link provided")
            exit(1)

        result = get_direct_link_from_doodstream(link)
        print(f"Direct Link: {result}")

    except Exception as err:
        print(f"Error: {err}")
        exit(1)
