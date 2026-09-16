"""Read the video URL from Gupload's encoded player configuration."""

import base64
import json
import re
from urllib.parse import urlparse

from curl_cffi import requests


_KEY_PARTS = re.compile(r"var\s+_p\s*=\s*\[(?P<parts>(?:\s*'[^']+'\s*,?)+)\]")
_CONFIG = re.compile(r"var\s+_cfg\s*=\s*_dp\('(?P<config>[^']+)'\)")


def get_direct_link_from_gupload(embed_url):
    parsed = urlparse(embed_url or "")
    if parsed.scheme != "https" or parsed.hostname != "gupload.xyz":
        raise ValueError("Invalid Gupload embed URL")

    response = requests.get(embed_url, impersonate="chrome124", timeout=20)
    response.raise_for_status()
    html = response.text or ""
    key_match = _KEY_PARTS.search(html)
    config_match = _CONFIG.search(html)
    if not key_match or not config_match:
        raise ValueError("Gupload player configuration not found")

    key = "".join(re.findall(r"'([^']+)'", key_match.group("parts"))).encode()
    if not key:
        raise ValueError("Gupload player key is empty")
    encoded = config_match.group("config").split("~", 1)
    if len(encoded) != 2:
        raise ValueError("Gupload player configuration is invalid")
    cipher = base64.b64decode(encoded[1])
    plain = bytes(value ^ key[index % len(key)] for index, value in enumerate(cipher))
    stream_url = json.loads(plain).get("videoUrl")
    if not isinstance(stream_url, str) or urlparse(stream_url).scheme != "https":
        raise ValueError("Gupload did not return a usable stream URL")
    return stream_url
