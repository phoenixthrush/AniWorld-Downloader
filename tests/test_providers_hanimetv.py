"""HanimeTV: front page -> a current title -> the stream it resolves itself.

Unlike the other sites this one is its own extractor: an episode resolves a
stream directly instead of pointing at VOE or Doodstream, so there is no
hoster map to walk.

Manual check, deliberately NOT part of the automated suite. It talks to the
live site and live hosters, so it fails whenever they change their markup,
block the runner or go down. Nothing here is named `test_*`, so pytest imports
this module and collects nothing, and a push stays green regardless.

    python tests/test_providers_hanimetv.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_stream_site

if __name__ == "__main__":
    sys.exit(run_stream_site("HanimeTV", "hanime_trending"))
