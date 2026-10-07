"""Manual live Filmo check. Optional arguments filter hosters (e.g. voe)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_site

if __name__ == "__main__":
    sys.exit(run_site("Filmo", "fetch_filmo_movies", [a.lower() for a in sys.argv[1:]]))
