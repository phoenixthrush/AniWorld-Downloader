import base64
import json
import logging
import re
from urllib.parse import urlparse

import niquests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, PROVIDER_HEADERS_D
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, PROVIDER_HEADERS_D

logger = logging.getLogger(__name__)

# -----------------------------
# Precompiled regex patterns
# -----------------------------
FILE_CODE_PATTERN = re.compile(r"/[de]/(?P<code>[a-zA-Z0-9]+)")
PACKED_JS_PATTERN = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(?P<p>[^']+)',\s*(?P<a>\d+),\s*(?P<c>\d+),\s*'(?P<k>[^']+)'\.split\('\|'\)",
    re.DOTALL,
)
SOURCE_PATTERN = re.compile(
    r"sources\s*:\s*\[\s*\{[^}]*file:\s*['\"](?P<url>[^'\"]+)['\"]", re.DOTALL
)
HLS_PATTERN = re.compile(r"['\"](?P<url>https?://[^'\"]+\.m3u8[^'\"]*)['\"]")
FILE_URL_PATTERN = re.compile(r"file\s*:\s*['\"](?P<url>https?://[^'\"]+)['\"]")


# -----------------------------
# Helper functions
# -----------------------------
def _base64url_decode(s):
    """Base64url decode (RFC 4648 section 5)."""
    s = s.replace("-", "+").replace("_", "/")
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.b64decode(s)


def _extract_file_code(url):
    """Extract the file code from a Filemoon/Byse URL.

    e.g., https://bysezejataos.com/d/56q7gpy3qyo6 -> 56q7gpy3qyo6
    """
    match = FILE_CODE_PATTERN.search(url)
    return match.group("code") if match else None


def _decrypt_payload(playback, key, iv_prop, payload_prop):
    """Decrypt an AES-256-GCM encrypted payload."""
    iv_str = playback.get(iv_prop)
    payload_str = playback.get(payload_prop)
    if not iv_str or not payload_str:
        return None

    iv = _base64url_decode(iv_str)
    ciphertext = _base64url_decode(payload_str)

    # AES-GCM: last 16 bytes are the auth tag
    tag_size = 16
    if len(ciphertext) <= tag_size:
        return None

    aesgcm = AESGCM(key)
    # cryptography library expects nonce + ciphertext+tag combined
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))


def _decrypt_playback_data(playback):
    """Decrypt AES-256-GCM encrypted playback data from the Byse API.

    The key is formed by base64url-decoding and concatenating key_parts.
    """
    key_parts = playback.get("key_parts")
    if not key_parts or not isinstance(key_parts, list):
        return None

    key_bytes = b""
    for part in key_parts:
        if not part:
            return None
        key_bytes += _base64url_decode(part)

    # Try primary payload first, then payload2
    result = _decrypt_payload(playback, key_bytes, "iv", "payload")
    if result is not None:
        return result

    return _decrypt_payload(playback, key_bytes, "iv2", "payload2")


def _extract_best_source_url(data):
    """Extract the best quality video URL from decrypted sources JSON."""
    # Try "sources" array
    sources = data.get("sources")
    if isinstance(sources, list) and sources:
        best_url = None
        best_height = 0
        for source in sources:
            url = source.get("url")
            height = source.get("height", 0)
            if url and isinstance(height, int) and height >= best_height:
                best_url = url
                best_height = height
        if best_url:
            return best_url

    # Try "source" property
    source = data.get("source")
    if isinstance(source, str) and source:
        return source

    # Try "file" property
    file_url = data.get("file")
    if isinstance(file_url, str) and file_url:
        return file_url

    return None


def _try_byse_api(embed_url, file_code, headers):
    """Try the modern Byse-style REST API with AES-256-GCM decryption."""
    try:
        parsed = urlparse(embed_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        api_url = f"{base_url}/api/videos/{file_code}"

        logger.debug("Trying Byse API: %s", api_url)

        resp = GLOBAL_SESSION.get(api_url, headers=headers)
        if resp.status_code != 200:
            logger.debug("Byse API returned %s", resp.status_code)
            return None

        data = resp.json()
        playback = data.get("playback")
        if not playback:
            logger.debug("No playback data in API response")
            return None

        decrypted = _decrypt_playback_data(playback)
        if decrypted is None:
            logger.warning("Failed to decrypt Byse playback data")
            return None

        best_url = _extract_best_source_url(decrypted)
        if best_url:
            logger.info("Filemoon/Byse: extracted stream URL via API")
            return best_url

    except Exception as err:
        logger.debug("Byse API approach failed: %s", err)

    return None


def _decode_base_n(token, radix):
    """Convert a string from base-N to a decimal integer (up to base 62)."""
    if radix <= 10:
        try:
            return int(token)
        except ValueError:
            return -1

    result = 0
    for c in token:
        if "0" <= c <= "9":
            digit = ord(c) - ord("0")
        elif "a" <= c <= "z":
            digit = ord(c) - ord("a") + 10
        elif "A" <= c <= "Z":
            digit = ord(c) - ord("A") + 36
        else:
            return -1

        if digit >= radix:
            return -1
        result = result * radix + digit

    return result


def _unpack_js(packed, radix, count, keywords):
    """Unpack Dean Edwards' packed JavaScript (legacy Filemoon)."""

    def replacer(match):
        token = match.group(1)
        index = _decode_base_n(token, radix)
        if 0 <= index < len(keywords) and keywords[index]:
            return keywords[index]
        return token

    return re.sub(r"\b(\w+)\b", replacer, packed)


def _extract_url_from_string(text):
    """Extract a video URL from text content."""
    hls_match = HLS_PATTERN.search(text)
    if hls_match:
        return hls_match.group("url")

    src_match = SOURCE_PATTERN.search(text)
    if src_match:
        return src_match.group("url")

    file_match = FILE_URL_PATTERN.search(text)
    if file_match:
        url = file_match.group("url")
        if ".m3u8" in url.lower() or ".mp4" in url.lower():
            return url

    return None


def _try_extract_from_html(html):
    """Try to extract video URL from HTML (legacy Filemoon with packed JS)."""
    # Try packed JS
    match = PACKED_JS_PATTERN.search(html)
    if match:
        packed = match.group("p")
        radix = int(match.group("a"))
        keywords = match.group("k").split("|")

        unpacked = _unpack_js(packed, radix, 0, keywords)
        if unpacked:
            url = _extract_url_from_string(unpacked)
            if url:
                logger.info("Filemoon: extracted URL from packed JS")
                return url

    # Try direct patterns
    url = _extract_url_from_string(html)
    if url:
        logger.info("Filemoon: extracted URL from direct pattern in HTML")
    return url


# -----------------------------
# Main Filemoon functions
# -----------------------------
def get_direct_link_from_filemoon(embeded_filemoon_link, headers=None):
    """Get direct Filemoon video URL."""
    try:
        if headers is None:
            headers = PROVIDER_HEADERS_D.get(
                "Filemoon", {"User-Agent": DEFAULT_USER_AGENT}
            )

        # Strategy 1: Try modern Byse-style API (AES-256-GCM encrypted)
        file_code = _extract_file_code(embeded_filemoon_link)
        if file_code:
            api_url = _try_byse_api(embeded_filemoon_link, file_code, headers)
            if api_url:
                return api_url

        # Strategy 2: Try legacy HTML scraping (packed JS)
        resp = GLOBAL_SESSION.get(embeded_filemoon_link, headers=headers)
        resp.raise_for_status()
        html = resp.text

        url = _try_extract_from_html(html)
        if url:
            return url

        raise ValueError("No Filemoon video source found in page.")

    except niquests.RequestException as err:
        raise ValueError(f"Failed to fetch Filemoon page: {err}") from err


def get_preview_image_link_from_filemoon(embeded_filemoon_link, headers=None):
    """Get Filemoon preview image URL."""
    raise NotImplementedError(
        "get_preview_image_link_from_filemoon is not implemented yet."
    )


if __name__ == "__main__":
    # Tested on xxxx/xx/xx -> WORKING
    # Example: https://xxx

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter Filemoon Link: ").strip()
    if not link:
        print("Error: No link provided")
        exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_filemoon(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        print("Preview image:", get_preview_image_link_from_filemoon(link))
        print("=" * 25)

        print(
            f'mpv "{direct_link}" --http-header-fields=User-Agent: "{DEFAULT_USER_AGENT}"'
        )

        print("=" * 25)
    except ValueError as e:
        print("Error:", e)
