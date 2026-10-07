import argparse
import logging
import os
import sys

from packaging.version import parse as parse_version

from .anime4k import anime4k
from .config import (
    ACTION_METHODS,
    LANG_LABELS,
    SUPPORTED_PROVIDERS,
    VERSION,
    get_latest_version,
)
from .logger import get_logger

logger = get_logger(__name__)

EXAMPLES = r"""
Command-Line Examples

AniWorld Downloader supports direct downloads, playback, interactive search, and the Web UI.

Example 1: Download a Single Episode (default action)
To download episode 1 of "Demon Slayer: Kimetsu no Yaiba":
aniworld --no-menu https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 2: Download Multiple Episodes (default action)
To download multiple episodes of "Demon Slayer":
aniworld --no-menu \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-2

Example 3: Watch Episodes with Aniskip
To watch an episode while skipping intros and outros:
aniworld --no-menu --action Watch --aniskip \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 4: Syncplay with Friends (+ Keep Watching)
To Syncplay a specific episode with friends:
aniworld --no-menu --action Syncplay --keep-watching \
  --syncplay-host syncplay.pl:8998 \
  --syncplay-room "MyRoom" \
  --syncplay-username "phoenixthrush" \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Language Options for Syncplay

For German Dub:
aniworld --no-menu --action Syncplay --keep-watching --language "German Dub" --aniskip \
  --syncplay-host syncplay.pl:8998 --syncplay-room "MyRoom" --syncplay-username "phoenixthrush" \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

For English Sub:
aniworld --no-menu --action Syncplay --keep-watching --language "English Sub" --aniskip \
  --syncplay-host syncplay.pl:8998 --syncplay-room "MyRoom" --syncplay-username "phoenixthrush" \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

To derive a room name from the episode filename and a shared value:
Leave --syncplay-room unset; this is not a Syncplay server password.
aniworld --no-menu --action Syncplay --keep-watching --language "English Sub" --aniskip \
  --syncplay-host syncplay.pl:8998 --syncplay-username "phoenixthrush" \
  --syncplay-password beans \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 5: Download with Specific Provider and Language (default action)
To download using the VOE provider with English subtitles:
aniworld --no-menu --provider VOE --language "English Sub" \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 6: Use an Episode File (default action)
To download URLs listed in a file:
aniworld --no-menu --episode-file episodes.txt --language "German Dub"

Example 7: Use a custom provider URL
Replace the example URL with a real provider page URL.
The resolved media is saved as input.mkv in the configured download folder.
Specify --provider so the matching extractor and headers are used.
aniworld --provider VOE --provider-url "https://voe.sx/e/example"

Example 8: Choose a Download Folder and Action
Set the download folder explicitly:
aniworld --no-menu --action Download --output "./downloads" \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 9: Pick a Random Anime
Pick a random AniWorld title, then choose episodes in the terminal menu:
aniworld --random-anime

Example 10: Search SerienStream
Search for a series interactively using SerienStream:
aniworld --use-sto-search

Example 11: Configure Anime4K for Playback
Install the high-end GPU shaders and watch an episode:
aniworld --no-menu --action Watch --anime4k High \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Use the low-end GPU shaders instead:
aniworld --no-menu --action Watch --anime4k Low \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Remove the Anime4K shaders before watching:
aniworld --no-menu --action Watch --anime4k Remove \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Anime4K configures MPV playback shaders; it does not upscale downloaded files.

Example 12: Start the Web UI Locally
Start the Web UI on the default port (8080) and open it in your browser:
aniworld --web-ui

Example 13: Run the Web UI on Your Network
Listen on all interfaces on port 8081, enable local accounts, and skip opening a browser:
aniworld --web-ui --web-port 8081 --web-expose --web-auth --no-browser

Example 14: Enable Web UI SSO
Install the optional SSO dependency with: python -m pip install "aniworld[sso]"
Set ANIWORLD_OIDC_ISSUER_URL, ANIWORLD_OIDC_CLIENT_ID, and
ANIWORLD_OIDC_CLIENT_SECRET in your .env first.
Enable local accounts and OIDC login:
aniworld --web-ui --web-auth --web-sso

Example 15: Require SSO Login
With the same SSO dependency and OIDC settings, allow only OIDC login:
aniworld --web-ui --web-force-sso

Example 16: Enable Debug Logging
Download an episode with detailed logs:
aniworld --no-menu --debug \
  https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1

Example 17: Show Help, Version, or Examples
Show the complete argument reference:
aniworld --help

Show the installed version and check for updates:
aniworld --version

Show this list of examples:
aniworld --examples

Notes
- --aniskip and --keep-watching can be combined with Watch and Syncplay.
- Download is the default action. --no-menu processes URLs directly.
- URLs are positional arguments, so you can paste one or many at the end of the command.
- The selected language must be available for the episode.
- The preferred provider is tried first, with fallback to other available providers.
- AniSkip depends on available metadata and timing data.
- Site URLs and hoster availability can change.
""".strip()


def parse_args():
    parser = argparse.ArgumentParser(
        prog="aniworld",
        description=(
            "AniWorld Downloader is a cross-platform tool for streaming and "
            "downloading anime from aniworld.to, as well as movies and series "
            "from serienstream.to. It runs on Windows, macOS, and Linux, providing a "
            "seamless experience for offline viewing or instant playback."
        ),
        epilog='Run "aniworld --examples" to see more usage examples.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # =========================
    # General / Core options
    # =========================
    general = parser.add_argument_group("General Options")
    general.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    general.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Show version information and exit",
    )
    general.add_argument(
        "-nm",
        "--no-menu",
        action="store_true",
        help="Disable interactive menu",
    )
    general.add_argument(
        "-x",
        "--examples",
        action="store_true",
        help="Show extended command-line examples and exit",
    )

    # =========================
    # Playback / Download options
    # =========================
    playback = parser.add_argument_group("Playback & Download Options")
    playback.add_argument(
        "-a",
        "--action",
        choices=sorted(ACTION_METHODS.keys()),
        help="Choose action method",
    )
    playback.add_argument(
        "-l",
        "--language",
        choices=sorted(LANG_LABELS.values()),
        help="Choose language",
    )
    playback.add_argument(
        "-p",
        "--provider",
        choices=sorted(SUPPORTED_PROVIDERS),
        help="Choose provider",
    )

    playback.add_argument(
        "-sk",
        "--aniskip",
        action="store_true",
        help="Skip intros/outros when watching (AniSkip integration)",
    )
    playback.add_argument(
        "-kw",
        "--keep-watching",
        action="store_true",
        help="Automatically continue with the next episode",
    )
    playback.add_argument(
        "-o",
        "--output",
        help="Output file path",
    )

    # =========================
    # Discovery / Random
    # =========================
    discovery = parser.add_argument_group("Discovery Options")
    discovery.add_argument(
        "-r",
        "--random-anime",
        action="store_true",
        help="Fetch a random anime series",
    )
    discovery.add_argument(
        "-sto",
        "--use-sto-search",
        action="store_true",
        help="Prefer serienstream.to for interactive searches.",
    )

    # =========================
    # Anime4K
    # =========================
    a4k = parser.add_argument_group("Anime4K Options")
    a4k.add_argument(
        "-A",
        "--anime4k",
        choices=["High", "Low", "Remove"],
        help="Enable Anime4K upscaling with specified mode",
    )

    # =========================
    # Input sources
    # =========================
    inputs = parser.add_argument_group("Input Options")
    inputs.add_argument(
        "-f",
        "--episode-file",
        help="Path to a text file containing episode URLs (one URL per line)",
    )
    inputs.add_argument(
        "url",
        nargs="*",
        help="URLs of series, season, or episodes",
    )

    # =========================
    # Provider direct URL (custom)
    # =========================
    provider = parser.add_argument_group("Provider URL Options")
    provider.add_argument(
        "-pu",
        "--provider-url",
        help="Custom provider URL",
    )

    # =========================
    # WebUI
    # =========================
    webui = parser.add_argument_group("WebUI Options")
    webui.add_argument(
        "-w",
        "--web-ui",
        action="store_true",
        help="Start the web UI",
    )

    webui.add_argument(
        "-wP",
        "--web-port",
        type=int,
        default=8080,
        help="Port for the web UI (default: 8080)",
    )

    webui.add_argument(
        "-wN",
        "--no-browser",
        action="store_true",
        help="Don't open the browser automatically when starting the web UI",
    )

    webui.add_argument(
        "-wE",
        "--web-expose",
        action="store_true",
        help="Bind the web UI to all interfaces (0.0.0.0) instead of localhost only",
    )

    webui.add_argument(
        "-wA",
        "--web-auth",
        action="store_true",
        help="Enable local authentication for the web UI",
    )

    webui.add_argument(
        "-wS",
        "--web-sso",
        action="store_true",
        help="Enable SSO (OIDC) login for the web UI",
    )

    webui.add_argument(
        "-wFS",
        "--web-force-sso",
        action="store_true",
        help="Force SSO-only authentication (implies --web-auth and --web-sso)",
    )

    # =========================
    # Syncplay (only meaningful with --action Syncplay)
    # =========================
    syncplay = parser.add_argument_group(
        "Syncplay Options (requires --action Syncplay)"
    )
    syncplay.add_argument(
        "-sH",
        "--syncplay-host",
        help="Specify the Syncplay server host",
    )
    syncplay.add_argument(
        "-sR",
        "--syncplay-room",
        help="Specify the Syncplay room name (overrides the generated name)",
    )
    syncplay.add_argument(
        "-sU",
        "--syncplay-username",
        help="Specify the Syncplay username",
    )
    syncplay.add_argument(
        "-sP",
        "--syncplay-password",
        help=(
            "Seed the generated room name. Ignored when a room is set; "
            "does not authenticate to the Syncplay server."
        ),
    )

    args = parser.parse_args()

    if args.examples:
        print(EXAMPLES)
        raise SystemExit(0)

    if args.language:
        os.environ["ANIWORLD_LANGUAGE"] = args.language

    if args.provider:
        os.environ["ANIWORLD_PROVIDER"] = args.provider

    if args.random_anime:
        os.environ["ANIWORLD_RANDOM_ANIME"] = "1"

    if args.no_menu:
        os.environ["ANIWORLD_NO_MENU"] = "1"

    if args.aniskip:
        os.environ["ANIWORLD_ANISKIP"] = "1"

    if args.keep_watching:
        os.environ["ANIWORLD_KEEP_WATCHING"] = "1"

    if args.use_sto_search:
        os.environ["ANIWORLD_USE_STO_SEARCH"] = "1"

    if args.output:
        os.environ["ANIWORLD_DOWNLOAD_PATH"] = (
            os.path.abspath(args.output)
            if not os.path.isabs(args.output)
            else args.output
        )

    if args.anime4k:
        mode = args.anime4k.lower()
        logger.debug(f"Anime4K upscaling set to: {mode}")
        anime4k(mode)

    if args.debug:
        os.environ["ANIWORLD_DEBUG_MODE"] = "1"

        logging.getLogger().setLevel(logging.DEBUG)
        for name in logging.Logger.manager.loggerDict:
            logging.getLogger(name).setLevel(logging.DEBUG)

        logger.debug("Debug mode enabled")

    if args.action == "Syncplay":
        if args.syncplay_host:
            os.environ["ANIWORLD_SYNCPLAY_HOST"] = args.syncplay_host
        if args.syncplay_room:
            os.environ["ANIWORLD_SYNCPLAY_ROOM"] = args.syncplay_room
        if args.syncplay_username:
            os.environ["ANIWORLD_SYNCPLAY_USERNAME"] = args.syncplay_username
        if args.syncplay_password:
            os.environ["ANIWORLD_SYNCPLAY_PASSWORD"] = args.syncplay_password

    if args.episode_file:
        try:
            with open(args.episode_file, "r") as f:
                for line in f:
                    u = line.strip()
                    if u:
                        args.url.append(u)
            logger.debug(f"Loaded {len(args.url)} URLs from {args.episode_file}")
        except Exception as e:
            logger.error(f"Failed to read episode file: {e}")
            sys.exit(1)

    if args.provider_url and args.provider:
        import ffmpeg

        from .config import PROVIDER_HEADERS_D
        from .extractors import provider_functions

        provider_key = (args.provider or "").strip()
        headers = PROVIDER_HEADERS_D.get(provider_key, {})

        headers_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

        direct_link = provider_functions[
            f"get_direct_link_from_{provider_key.lower()}"
        ](args.provider_url)

        download_dir = os.getenv("ANIWORLD_DOWNLOAD_PATH", ".")
        output_path = os.path.join(download_dir, "input.mkv")

        (
            ffmpeg.input(
                direct_link,
                headers=headers_str if headers_str else None,
            )
            .output(
                output_path,
                c="copy",
                f="matroska",
            )
            .run()
        )

        sys.exit(0)

    if args.version:
        installed_version = VERSION or "unknown"
        latest_version = get_latest_version()
        is_latest = bool(
            latest_version
            and VERSION
            and parse_version(VERSION) >= parse_version(latest_version)
        )

        if not VERSION:
            version_message = "Could not determine the installed version."
        elif not latest_version:
            version_message = "Could not check the latest version."
        elif is_latest:
            version_message = "You are on the latest version."
        else:
            version_message = f"Your version is outdated.\nPlease update to the latest version (v.{latest_version})."

        cowsay = Rf"""______________________________
< AniWorld-Downloader v.{installed_version} >
------------------------------
    \   ^__^
     \  (oo)\_______
        (__)\       )\/\
            ||----w |
            ||     ||

{version_message}"""

        print(cowsay.strip())
        sys.exit(0)

    return args
