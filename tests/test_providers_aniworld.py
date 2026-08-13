"""AniWorld: front page -> a current title -> episode -> every hoster it offers.

Manual check, deliberately NOT part of the automated suite. It talks to the
live site and live hosters, so it fails whenever they change their markup,
block the runner or go down. Nothing here is named `test_*`, so pytest imports
this module and collects nothing, and a push stays green regardless.

    python tests/test_providers_aniworld.py
    python tests/test_providers_aniworld.py voe dood   # only matching hosters
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_site

if __name__ == "__main__":
    sys.exit(
        run_site("AniWorld", "fetch_new_animes", [a.lower() for a in sys.argv[1:]])
    )
