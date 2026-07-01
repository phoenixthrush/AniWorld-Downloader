import re

import niquests

try:
    from ...config import DEFAULT_USER_AGENT
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT


def get_direct_link_from_megakino(embeded_megakino_link, headers=None):
    """Get direct Megakino video URL."""
    page_html = _fetch_megakino_player_page(embeded_megakino_link, headers=headers)
    stream_parts = _extract_megakino_stream_parts(page_html)
    if not stream_parts:
        return None

    uid, md5, video_id = stream_parts

    stream_link = f"https://watch.gxplayer.xyz/m3u8/{uid}/{md5}/master.txt?s=1&id={video_id}&cache=1"
    return stream_link


def _fetch_megakino_player_page(embeded_megakino_link, headers=None):
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)

    response = niquests.get(
        embeded_megakino_link,
        timeout=15,
        headers=request_headers,
    )
    response.raise_for_status()
    return response.text


def _extract_megakino_stream_parts(page_html):
    patterns = {
        "uid": re.compile(r'"uid"\s*:\s*"([^"]+)"'),
        "md5": re.compile(r'"md5"\s*:\s*"([^"]+)"'),
        "id": re.compile(r'"id"\s*:\s*"([^"]+)"'),
    }

    extracted = {}
    for key, pattern in patterns.items():
        match = pattern.search(page_html)
        if not match:
            return None
        extracted[key] = match.group(1)

    return extracted["uid"], extracted["md5"], extracted["id"]


def get_preview_image_link_from_megakino(embeded_megakino_link, headers=None):
    """Get Megakino preview image URL."""
    raise NotImplementedError(
        "get_preview_image_link_from_megakino is not implemented yet."
    )


if __name__ == "__main__":
    # Tested on xxxx/xx/xx -> WORKING
    # Example: https://xxx

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter Megakino Link: ").strip()
    if not link:
        print("Error: No link provided")
        exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_megakino(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        print("Preview image:", get_preview_image_link_from_megakino(link))
        print("=" * 25)

        print(
            f'mpv "{direct_link}" --http-header-fields=User-Agent: "{DEFAULT_USER_AGENT}"'
        )

        print("=" * 25)
    except ValueError as e:
        print("Error:", e)
