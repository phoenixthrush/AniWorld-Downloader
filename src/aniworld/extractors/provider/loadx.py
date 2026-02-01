import requests
import json
import logging
import sys
from typing import Dict, Optional
from urllib.parse import urlparse

from ...config import DEFAULT_REQUEST_TIMEOUT, REQUEST_VERIFY

# Setup module logger
logger = logging.getLogger(__name__)


def _validate_loadx_url(url: str) -> str:
    """
    Validate and clean the LoadX URL.

    Args:
        url: URL to validate

    Returns:
        Validated and cleaned URL

    Raises:
        ValueError: If URL is invalid
    """
    if not url or not url.strip():
        raise ValueError("LoadX URL cannot be empty")

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL format - must start with http:// or https://")

    try:
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            raise ValueError("Invalid URL format - missing domain")
    except Exception as err:
        raise ValueError(f"Invalid URL format: {err}") from err

    return url


def _make_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
) -> requests.Response:
    """
    Make HTTP request with error handling.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, HEAD)
        headers: Optional headers dictionary
        allow_redirects: Whether to follow redirects

    Returns:
        HTTP response object

    Raises:
        ValueError: If request fails
    """
    try:
        logger.debug(f"Making {method} request to: {url}")

        if method.upper() == "HEAD":
            response = requests.head(
                url,
                allow_redirects=allow_redirects,
                verify=REQUEST_VERIFY,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                headers=headers or {},
            )
        elif method.upper() == "POST":
            response = requests.post(
                url,
                headers=headers or {},
                verify=REQUEST_VERIFY,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )
        else:
            response = requests.get(
                url,
                headers=headers or {},
                verify=REQUEST_VERIFY,
                timeout=DEFAULT_REQUEST_TIMEOUT,
            )

        response.raise_for_status()
        return response

    except requests.RequestException as err:
        logger.error(f"Request failed for {url}: {err}")
        raise ValueError(f"Failed to fetch URL: {err}") from err


def _extract_id_hash_from_url(url: str) -> tuple[str, str]:
    """
    Extract ID hash and host from LoadX URL.

    Args:
        url: LoadX URL

    Returns:
        Tuple of (id_hash, host)

    Raises:
        ValueError: If URL structure is invalid
    """
    try:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split("/")

        if len(path_parts) < 3:
            raise ValueError(
                "Invalid LoadX URL structure - insufficient path components"
            )

        id_hash = path_parts[2]
        host = parsed_url.netloc

        if not id_hash:
            raise ValueError("Invalid LoadX URL - missing ID hash")

        if not host:
            raise ValueError("Invalid LoadX URL - missing host")

        return id_hash, host

    except Exception as err:
        logger.error(f"Failed to extract ID hash from URL: {err}")
        raise ValueError(f"Failed to parse LoadX URL: {err}") from err


def _parse_video_response(response_text: str) -> str:
    """
    Parse video URL from response text.

    Args:
        response_text: JSON response text

    Returns:
        Video URL

    Raises:
        ValueError: If parsing fails or video URL not found
    """
    try:
        if not response_text:
            raise ValueError("Empty response received")

        data = json.loads(response_text)
        video_url = data.get("videoSource")

        if not video_url:
            raise ValueError("No video source found in response")

        if not isinstance(video_url, str) or not video_url.strip():
            raise ValueError("Invalid video URL format")

        return video_url.strip()

    except json.JSONDecodeError as err:
        logger.error(f"Failed to parse JSON response: {err}")
        raise ValueError(f"Invalid JSON response: {err}") from err
    except Exception as err:
        logger.error(f"Failed to parse video response: {err}")
        raise ValueError(f"Failed to parse video data: {err}") from err


def get_direct_link_from_loadx(embeded_loadx_link: str) -> str:
    """
    Extract direct video link from LoadX embedded URL.

    Args:
        embeded_loadx_link: LoadX embedded URL

    Returns:
        Direct video URL

    Raises:
        ValueError: If extraction fails
    """
    try:
        # Validate input URL
        validated_url = _validate_loadx_url(embeded_loadx_link)
        logger.info(f"Extracting video from LoadX URL: {validated_url}")

        # Follow redirects to get actual URL
        response = _make_request(validated_url, method="HEAD", allow_redirects=True)

        # Extract ID hash and host from final URL
        id_hash, host = _extract_id_hash_from_url(response.url)

        # Build API endpoint URL
        post_url = f"https://{host}/player/index.php?data={id_hash}&do=getVideo"
        logger.debug(f"Making API request to: {post_url}")

        # Make API request
        headers = {"X-Requested-With": "XMLHttpRequest"}
        api_response = _make_request(post_url, method="POST", headers=headers)

        # Parse response and extract video URL
        video_url = _parse_video_response(api_response.text)

        logger.info(f"Successfully extracted video URL: {video_url}")
        return video_url

    except ValueError:
        raise
    except Exception as err:
        logger.error(f"Unexpected error extracting LoadX video: {err}")
        raise ValueError(f"Failed to extract video from LoadX: {err}") from err


def validate_video_url(url: str) -> bool:
    """
    Validate if a video URL is accessible.

    Args:
        url: Video URL to validate

    Returns:
        True if video is accessible, False otherwise
    """
    try:
        response = requests.head(url, timeout=DEFAULT_REQUEST_TIMEOUT)
        return response.status_code == 200
    except requests.RequestException:
        return False


def main() -> None:
    """
    Main function for standalone execution.

    Handles command-line execution with proper error handling and logging.
    """
    # Setup logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Get URL from command line arguments or user input
        if len(sys.argv) > 1:
            url = sys.argv[1]
        else:
            url = input("Enter LoadX Link: ").strip()

        if not url:
            print("No URL provided.")
            sys.exit(1)

        # Extract video URL
        video_url = get_direct_link_from_loadx(url)
        print(f"Direct video URL: {video_url}")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
    except ValueError as err:
        print(f"Error: {err}")
        logger.error(f"LoadX extraction error: {err}")
        sys.exit(1)
    except Exception as err:
        print(f"Unexpected error: {err}")
        logger.error(f"Unexpected error: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
