"""Every hoster extractor on its own, independent of any site.

The per-site files answer whether a site still works. This one answers
whether a hoster's extractor still works, by running each against a known
embed URL. Those URLs point at one specific video each, so they go stale
when it is taken down: a 404 here usually means the video is gone, not that
the extractor broke. Swap in any current embed URL from that hoster.

Manual check, deliberately NOT part of the automated suite. It talks to the
live site and live hosters, so it fails whenever they change their markup,
block the runner or go down. Nothing here is named `test_*`, so pytest imports
this module and collects nothing, and a push stays green regardless.

    python tests/test_providers_hosters.py
    python tests/test_providers_hosters.py voe   # only matching hosters
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_hosters

if __name__ == "__main__":
    sys.exit(run_hosters([a.lower() for a in sys.argv[1:]]))
