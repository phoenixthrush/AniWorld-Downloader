# ========================
# Nuitka project configuration
# ========================

# Basic flags
# nuitka-project: --static-libpython=no
# nuitka-project: --assume-yes-for-downloads
# nuitka-project: --python-flag=-m
# nuitka-project: --mode=app
# nuitka-project: --output-filename=AniWorldDownloader

# Include hidden imports (dynamically loaded modules that Nuitka can't detect)
# nuitka-project: --include-package=urllib3.contrib
# nuitka-project: --include-package=aniworld.extractors

# Include Patchright's Node-based browser installer driver.
# nuitka-project-set: patchright_driver = str(__import__("pathlib").Path(__import__("inspect").getfile(__import__("patchright"))).parent / "driver")
# nuitka-project: --include-raw-dir={patchright_driver}=patchright/driver

# Include data files/directories
# nuitka-project: --include-data-dir=src/aniworld/web/templates=aniworld/web/templates
# nuitka-project: --include-data-dir=src/aniworld/web/static=aniworld/web/static
# nuitka-project: --include-data-file=src/aniworld/.env.example=aniworld/.env.example
# nuitka-project: --include-data-file=src/aniworld/ascii/ASCII.txt=aniworld/ascii/ASCII.txt
# nuitka-project: --include-data-file=src/aniworld/aniskip/scripts/aniskip.lua=aniworld/aniskip/scripts/aniskip.lua
# nuitka-project: --include-data-file=src/aniworld/aniskip/scripts/autoexit.lua=aniworld/aniskip/scripts/autoexit.lua
# nuitka-project: --include-data-file=src/aniworld/aniskip/scripts/autostart.lua=aniworld/aniskip/scripts/autostart.lua
# nuitka-project: --include-data-file=src/aniworld/browsers.jsonl=aniworld/browsers.jsonl

# Platform-specific flags
# nuitka-project-if: {OS} == "Darwin":
#    nuitka-project: --macos-app-name=AniWorld
#    nuitka-project: --macos-app-icon=src/aniworld/nuitka/icon.webp

# nuitka-project-if: {OS} in ("Windows", "Linux", "FreeBSD"):
#    nuitka-project: --windows-icon-from-ico=src/aniworld/nuitka/icon.webp

# ========================
# Python entrypoint
# ========================

import sys

from .entry import aniworld


def main():
    return aniworld()


if __name__ == "__main__":
    sys.exit(main())
