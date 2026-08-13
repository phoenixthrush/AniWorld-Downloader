import re
import sys

try:
    from ...config import GLOBAL_SESSION
except ImportError:
    from aniworld.config import GLOBAL_SESSION

# -----------------------------
# Constants
# -----------------------------
FILE_LINK_PATTERN = re.compile(r'file\s*:\s*[\'"]([^\'"]+?\.m3u8[^\'"]*)[\'"]')
PREVIEW_IMAGE_PATTERN = re.compile(
    r'image\s*:\s*[\'"]([^\'"]+\.(?:jpg|jpeg|png|webp))[\'"]'
)


# -----------------------------
# Helper Functions
# -----------------------------
def _get_headers():
    """Return headers for Vidmoly requests."""
    return {"Referer": "https://vidmoly.biz"}


def _extract_regex(pattern, content, name, url):
    """Extract regex match or raise ValueError."""
    if not content:
        raise ValueError(f"No HTML content for {url}")
    match = pattern.search(content)
    if not match:
        raise ValueError(f"{name} not found in {url}")
    return match.group(1)


def _extract_script_content(html):
    """Return all script contents concatenated."""
    scripts = re.findall(
        r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE
    )
    return "\n".join(filter(None, scripts))  # join non-empty scripts


# -----------------------------
# Main Vidmoly Functions
# -----------------------------
def get_direct_link_from_vidmoly(embed_url):
    """Get direct Vidmoly video link."""
    if not embed_url:
        raise ValueError("Embed URL cannot be empty")

    resp = GLOBAL_SESSION.get(embed_url, headers=_get_headers())
    resp.raise_for_status()
    html = resp.text

    script_content = _extract_script_content(html)
    return _extract_regex(
        FILE_LINK_PATTERN, script_content, "Direct video URL", embed_url
    )


def get_preview_image_link_from_vidmoly(embed_url):
    """Get Vidmoly preview image URL."""
    if not embed_url:
        raise ValueError("Embed URL cannot be empty")

    resp = GLOBAL_SESSION.get(embed_url, headers=_get_headers())
    resp.raise_for_status()
    html = resp.text

    script_content = _extract_script_content(html)
    return _extract_regex(
        PREVIEW_IMAGE_PATTERN, script_content, "Preview image URL", embed_url
    )


if __name__ == "__main__":
    # Tested on 2026/02/18 -> WORKING
    # Example: https://vidmoly.net/embed-zquo82b8dm1k.html

    link = input("Enter Vidmoly Link: ").strip()
    if not link:
        print("Error: No link provided")
        sys.exit(1)

    try:
        print("=" * 25)

        direct_link = get_direct_link_from_vidmoly(link)
        print("Direct link:", direct_link)
        print("=" * 25)

        preview_img = get_preview_image_link_from_vidmoly(link)
        print("Preview image:", preview_img)
        print("=" * 25)

        print(
            f'mpv --http-header-fields="Referer: https://vidmoly.biz" "{direct_link}"'
        )
        print("=" * 25)

    except Exception as e:
        print("Error:", e)
        sys.exit(1)
