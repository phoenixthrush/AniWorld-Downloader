"""Manual live HentaiTV check. Pass a search keyword; defaults to 'kanojo'."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provider_check import run_stream_site

if __name__ == "__main__":
    sys.exit(
        run_stream_site(
            "HentaiTV", "query_hentai_tv", " ".join(sys.argv[1:]) or "kanojo"
        )
    )
