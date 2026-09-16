"""Resolve the XFileSharing player used by moflix-stream.click."""

import json
import re
from urllib.parse import urlparse

from curl_cffi import requests

from .filemoon import _unpack_js


_PACKED_PLAYER = re.compile(
    r"eval\(function\(p,a,c,k,e,d\).*?\}\('(?P<p>(?:\\.|[^'\\])*)',"
    r"\s*(?P<radix>\d+),\s*\d+,\s*'(?P<keywords>(?:\\.|[^'\\])*)'"
    r"\.split\('\|'\)\)\)",
    re.DOTALL,
)
_LINKS = re.compile(r"var\s+links\s*=\s*(\{[^}]+\})")


def get_direct_link_from_moflixclick(embed_url):
    parsed = urlparse(embed_url or "")
    if parsed.scheme != "https" or parsed.hostname != "moflix-stream.click":
        raise ValueError("Invalid MoflixClick embed URL")

    response = requests.get(embed_url, impersonate="chrome124", timeout=20)
    response.raise_for_status()
    match = _PACKED_PLAYER.search(response.text or "")
    if match is None:
        raise ValueError("MoflixClick player data not found")

    unpacked = _unpack_js(
        match.group("p").replace("\\'", "'"),
        int(match.group("radix")),
        0,
        match.group("keywords").split("|"),
    )
    links_match = _LINKS.search(unpacked)
    if links_match is None:
        raise ValueError("MoflixClick stream links not found")
    links = json.loads(links_match.group(1))
    # The player itself tries hls4, then hls3, then hls2. The hls3 URL may
    # end in .txt even though its response is an HLS master playlist.
    for key in ("hls4", "hls3", "hls2"):
        url = links.get(key)
        if isinstance(url, str) and urlparse(url).scheme == "https":
            return url
    raise ValueError("MoflixClick has no usable stream URL")
