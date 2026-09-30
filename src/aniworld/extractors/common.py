"""Shared parsing helpers for streaming-site extraction."""

import base64
import json
import re
from html import unescape

_JSON_LD = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def walk_objects(value):
    """Yield dictionaries from nested JSON objects and arrays."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def extract_video_metadata(html):
    """Read the first JSON-LD VideoObject, including arrays and @graph blocks."""
    for raw in _JSON_LD.findall(html):
        try:
            value = json.loads(unescape(raw.strip()))
        except ValueError:
            continue
        for item in walk_objects(value):
            if item.get("@type") == "VideoObject":
                return item
    return {}


def decode_base64url(value):
    """Decode padded or unpadded base64url text or bytes."""
    if isinstance(value, str):
        value = value.encode("ascii")
    return base64.urlsafe_b64decode(value + b"=" * (-len(value) % 4))


def _decode_base_n(token, radix):
    """Convert a string from base-N to a decimal integer (up to base 62)."""
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = 0
    for char in token:
        digit = alphabet.find(char)
        if not 0 <= digit < radix:
            return -1
        result = result * radix + digit
    return result


def unpack_js(packed, radix, keywords):
    """Unpack Dean Edwards' packed JavaScript."""

    def replacer(match):
        token = match.group(1)
        index = _decode_base_n(token, radix)
        if 0 <= index < len(keywords) and keywords[index]:
            return keywords[index]
        return token

    return re.sub(r"\b(\w+)\b", replacer, packed)
