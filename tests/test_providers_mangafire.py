"""MangaFire: top titles -> a chapter -> its page images.

MangaFire has no video hoster at all, so checking it against the extractor
registry would prove nothing. What matters is that a title still resolves to
a chapter and that chapter to real page image URLs, which is its whole
download path.

Manual check, deliberately NOT part of the automated suite. It talks to the
live site and live hosters, so it fails whenever they change their markup,
block the runner or go down. Nothing here is named `test_*`, so pytest imports
this module and collects nothing, and a push stays green regardless.

    python tests/test_providers_mangafire.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_image_site

if __name__ == "__main__":
    sys.exit(run_image_site("MangaFire", "mangafire_trending"))
