"""Thin HTTP helpers shared by the scraping models.

They wrap the project's GLOBAL_SESSION so every site model fetches pages with
the same browser-like headers and DoH resolver, and adds an opt-in captcha
check that raises a readable error instead of silently parsing a challenge
page.
"""

try:
    from ...config import GLOBAL_SESSION
except ImportError:
    from aniworld.config import GLOBAL_SESSION

_CAPTCHA_HINTS = (
    "cf-challenge",
    "captcha",
    "just a moment",
    "verifizierung",
    "verification required",
    "attention required",
)


class CaptchaRequired(RuntimeError):
    """Raised when a page looks like a Cloudflare / captcha challenge."""


def get_session():
    """Return the shared HTTP session."""
    return GLOBAL_SESSION


def is_captcha_page(html, status_code=200):
    if status_code in (403, 429, 503):
        return True
    lowered = (html or "")[:4000].lower()
    return any(hint in lowered for hint in _CAPTCHA_HINTS)


def get_html(url, headers=None, timeout=20, check_captcha=True):
    """GET a URL and return its text, raising CaptchaRequired on a challenge.

    Forces gzip/deflate so responses are always decodable: several of the
    German mirror sites serve Brotli, which niquests can only decode when the
    optional brotli package is present. Without it the body comes back as
    undecoded bytes and every parser silently finds nothing.
    """
    request_headers = {"Accept-Encoding": "gzip, deflate"}
    if headers:
        request_headers.update(headers)
    resp = GLOBAL_SESSION.get(url, headers=request_headers, timeout=timeout)
    resp.raise_for_status()
    text = resp.text
    if check_captcha and is_captcha_page(text, resp.status_code):
        raise CaptchaRequired(f"captcha / challenge page for {url}")
    return text
