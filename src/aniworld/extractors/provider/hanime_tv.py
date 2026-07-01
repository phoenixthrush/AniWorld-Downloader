# TODO:
# replace requests with niquests later
# GLOBAL_SESSION does not load images yet, maybe because of bad headers
# should use the GLOBAL_SESSION here too for the shared dns resolver and stuff

import niquests

try:
    from ...config import DEFAULT_USER_AGENT, logger
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, logger


HANIME_VIDEO_API = "https://hanime.tv/api/v8/video?id={slug}"
_HANIME_HEADERS = {"User-Agent": DEFAULT_USER_AGENT}


def fetch_hanime_api_data(slug):
    api_url = HANIME_VIDEO_API.format(slug=slug)
    logger.debug(f"fetching hanime API ({api_url})...")
    resp = niquests.get(api_url, headers=_HANIME_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_direct_link_from_hanime_tv(api_data):
    """Extract the best-quality stream URL from hanime.tv API data."""
    manifest = api_data.get("videos_manifest") or {}
    servers = manifest.get("servers") or []

    best_url = None
    best_height = 0

    for server in servers:
        for stream in server.get("streams") or []:
            url = stream.get("signed_url") or stream.get("url") or ""
            if not url:
                continue
            height = int(stream.get("height") or 0)
            if height > best_height:
                best_height = height
                best_url = url

    if not best_url:
        raise ValueError("No stream URL found in hanime API data")

    return best_url


def get_download_url_from_hanime_tv(api_data):
    """Extract the direct download URL from hanime.tv API data (pixeldrain etc)."""
    dl_url = api_data.get("dl_url") or ""
    if not dl_url:
        return None
    if "pixeldrain.com/d/" in dl_url:
        file_id = dl_url.rstrip("/").split("/")[-1]
        return f"https://pixeldrain.com/api/filesystem/{file_id}"
    return dl_url
