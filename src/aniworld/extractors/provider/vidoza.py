import re
import sys

import niquests

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION


# Compile regex pattern once for better performance
SOURCE_LINK_PATTERN = re.compile(r'src:\s*"([^"]+)"')
IMAGE_LINK_PATTERN = re.compile(r'poster:\s*"([^"]+)"')


def get_direct_link_from_vidoza(embeded_vidoza_link):
    """Get direct Vidoza video URL."""
    try:
        resp = GLOBAL_SESSION.get(
            embeded_vidoza_link, headers={"User-Agent": DEFAULT_USER_AGENT}
        )
        resp.raise_for_status()
        html = resp.text

        if "sourcesCode:" in html:
            match = SOURCE_LINK_PATTERN.search(html)
            if match:
                return match.group(1)

    except niquests.RequestException as err:
        raise ValueError(f"Failed to fetch Vidoza page: {err}") from err


def get_preview_image_link_from_vidoza(embeded_vidoza_link):
    """Get Vidoza preview image URL."""
    try:
        resp = GLOBAL_SESSION.get(
            embeded_vidoza_link, headers={"User-Agent": DEFAULT_USER_AGENT}
        )
        resp.raise_for_status()
        html = resp.text

        if "sourcesCode:" in html:
            match = IMAGE_LINK_PATTERN.search(html)
            if match:
                return match.group(1)

    except niquests.RequestException as err:
        raise ValueError(f"Failed to fetch Vidoza page: {err}") from err


if __name__ == "__main__":
    # Tested on 2026/01/27 -> WORKING
    # Example: https://videzz.net/embed-xneznizpludf.html

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter Vidoza Link: ").strip()
    if not link:
        print("Error: No link provided")
        sys.exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_vidoza(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        print("Preview image:", get_preview_image_link_from_vidoza(link))
        print("=" * 25)

        print(f'mpv "{direct_link}" --user-agent="{DEFAULT_USER_AGENT}"')

        print("=" * 25)
    except ValueError as e:
        print("Error:", e)
