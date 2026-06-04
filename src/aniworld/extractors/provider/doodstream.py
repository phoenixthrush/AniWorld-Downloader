import logging
import random
import re
import time
import warnings
from urllib.parse import urljoin, urlparse

from urllib3.exceptions import InsecureRequestWarning

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION
    from ...playwright.captcha import solve_captcha
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION
    from aniworld.playwright.captcha import solve_captcha

warnings.simplefilter("ignore", InsecureRequestWarning)

# -----------------------------
# Constants
# -----------------------------
DOODSTREAM_BASE_URL = "https://dood.li"
RANDOM_STRING_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
PASS_MD5_PATTERN = r"\$\.get\([\"']([^\"']*\/pass_md5\/[^\"']*)[\"']"
TOKEN_PATTERN = r"token=([a-zA-Z0-9]+)"


# -----------------------------
# Helper Functions
# -----------------------------
def _get_headers(referer=None):
    """Return headers for Doodstream requests."""
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Referer": referer or f"{DOODSTREAM_BASE_URL}/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",
    }


def _extract_regex(pattern, content, name, url):
    """Extract a regex match or raise ValueError."""
    match = re.search(pattern, content)
    if not match:
        raise ValueError(f"{name} not found in {url}")
    return match.group(1)


def _generate_random_string(length=10):
    """Generate a random alphanumeric string."""
    return "".join(random.choices(RANDOM_STRING_CHARS, k=length))


def _get_embed_page(embed_url, headers=None):
    """Fetch HTML content of the embed page."""
    headers = headers or _get_headers()
    resp = GLOBAL_SESSION.get(embed_url, headers=headers, verify=False)
    html = resp.text
    if "Just a moment..." in html and "cloudflare" in html.lower():
        logging.warning(
            "Cloudflare challenge on Doodstream - solving via browser: %s", resp.url
        )
        solve_captcha(embed_url)
        resp = GLOBAL_SESSION.get(embed_url, headers=headers, verify=False)
        html = resp.text
        if "Just a moment..." in html and "cloudflare" in html.lower():
            raise ValueError(f"Doodstream Cloudflare challenge unsolvable: {resp.url}")
    resp.raise_for_status()
    return html


def _get_base_url(url):
    """Return the scheme/netloc base URL for the active Doodstream mirror."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return DOODSTREAM_BASE_URL
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_pass_md5_url(embed_html, embed_url):
    """Extract the pass_md5 URL from embed HTML."""
    pass_md5_url = _extract_regex(
        PASS_MD5_PATTERN, embed_html, "pass_md5 URL", embed_url
    )
    if not pass_md5_url.startswith("http"):
        pass_md5_url = urljoin(_get_base_url(embed_url), pass_md5_url)
    return pass_md5_url


def _get_token(embed_html, embed_url):
    """Extract the token from embed HTML."""
    return _extract_regex(TOKEN_PATTERN, embed_html, "token", embed_url)


# -----------------------------
# Main Doodstream Functions
# -----------------------------
def get_direct_link_from_doodstream(embed_url):
    """Extract the direct video link from a Doodstream embed URL."""
    if not embed_url:
        raise ValueError("Embed URL cannot be empty")

    logging.info(f"Extracting Doodstream direct link from: {embed_url}")
    base_url = _get_base_url(embed_url)
    embed_headers = _get_headers(f"{base_url}/")
    md5_headers = _get_headers(embed_url)

    embed_html = _get_embed_page(embed_url, embed_headers)
    pass_md5_url = _get_pass_md5_url(embed_html, embed_url)
    token = _get_token(embed_html, embed_url)

    md5_resp = GLOBAL_SESSION.get(pass_md5_url, headers=md5_headers, verify=False)
    md5_resp.raise_for_status()
    video_base_url = md5_resp.text.strip()
    if not video_base_url:
        raise ValueError(f"Empty video base URL returned from {pass_md5_url}")

    random_str = _generate_random_string(10)
    expiry = int(time.time())
    direct_link = f"{video_base_url}{random_str}?token={token}&expiry={expiry}"

    logging.info("Successfully extracted Doodstream direct link")
    return direct_link


def get_preview_image_link_from_doodstream(embed_url):
    """Get the preview image URL from a Doodstream embed (not implemented)."""
    raise NotImplementedError("Preview image extraction is not implemented yet.")


if __name__ == "__main__":
    # Tested on 2026/01 -> WORKING
    # Example URLs: https://doodsearch.site

    # logging.basicConfig(level=logging.DEBUG)

    link = input("Enter Doodstream Link: ").strip()
    if not link:
        print("Error: No link provided")
        exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_doodstream(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        # Preview image extraction not yet implemented
        try:
            preview_img = get_preview_image_link_from_doodstream(link)
            print("Preview image:", preview_img)
        except NotImplementedError:
            print("Preview image: Not implemented")
        print("=" * 25)

        print(
            f"mpv --http-header-fields='Referer: {DOODSTREAM_BASE_URL}/' '{direct_link}'"
        )
        print("=" * 25)

    except Exception as e:
        print("Error:", e)
        exit(1)
