import argparse
import logging
import os
import sys

from packaging.version import parse as parse_version
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

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
console = Console()

EXAMPLES = r"""
[bold underline cyan]Command-Line Arguments Example[/]

[dim]AniWorld Downloader provides command-line options for downloading and streaming anime without relying on the interactive menu or webui.[/]

[bold yellow]Example 1: Download a Single Episode (default action)[/]
[dim]To download episode 1 of "Demon Slayer: Kimetsu no Yaiba":[/]
[green]aniworld[/] [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[bold yellow]Example 2: Download Multiple Episodes (default action)[/]
[dim]To download multiple episodes of "Demon Slayer":[/]
[green]aniworld[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-2[/]

[bold yellow]Example 3: Watch Episodes with Aniskip[/]
[dim]To watch an episode while skipping intros and outros:[/]
[green]aniworld[/] [magenta]--action[/] [cyan]Watch[/] [magenta]--aniskip[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[bold yellow]Example 4: Syncplay with Friends (+ Keep Watching)[/]
[dim]To Syncplay a specific episode with friends:[/]
[green]aniworld[/] [magenta]--action[/] [cyan]Syncplay[/] [magenta]--keep-watching[/] \
  [magenta]--syncplay-host[/] [cyan]syncplay.pl:8998[/] \
  [magenta]--syncplay-room[/] [cyan]"MyRoom"[/] \
  [magenta]--syncplay-username[/] [cyan]"phoenixthrush"[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[dim]Language Options for Syncplay[/]

[dim]For German Dub:[/]
[green]aniworld[/] [magenta]--action[/] [cyan]Syncplay[/] [magenta]--keep-watching[/] [magenta]--language[/] [cyan]"German Dub"[/] [magenta]--aniskip[/] \
  [magenta]--syncplay-host[/] [cyan]syncplay.pl:8998[/] [magenta]--syncplay-room[/] [cyan]"MyRoom"[/] [magenta]--syncplay-username[/] [cyan]"phoenixthrush"[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[dim]For English Sub:[/]
[green]aniworld[/] [magenta]--action[/] [cyan]Syncplay[/] [magenta]--keep-watching[/] [magenta]--language[/] [cyan]"English Sub"[/] [magenta]--aniskip[/] \
  [magenta]--syncplay-host[/] [cyan]syncplay.pl:8998[/] [magenta]--syncplay-room[/] [cyan]"MyRoom"[/] [magenta]--syncplay-username[/] [cyan]"phoenixthrush"[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[dim]To restrict access, set a password for the room:[/]
[green]aniworld[/] [magenta]--action[/] [cyan]Syncplay[/] [magenta]--keep-watching[/] [magenta]--language[/] [cyan]"English Sub"[/] [magenta]--aniskip[/] \
  [magenta]--syncplay-host[/] [cyan]syncplay.pl:8998[/] [magenta]--syncplay-room[/] [cyan]"MyRoom"[/] [magenta]--syncplay-username[/] [cyan]"phoenixthrush"[/] \
  [magenta]--syncplay-password[/] [cyan]beans[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[bold yellow]Example 5: Download with Specific Provider and Language (default action)[/]
[dim]To download using the VOE provider with English subtitles:[/]
[green]aniworld[/] [magenta]--provider[/] [cyan]VOE[/] [magenta]--language[/] [cyan]"English Sub"[/] \
  [blue]https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1[/]

[bold yellow]Example 6: Use an Episode File (default action)[/]
[dim]To download URLs listed in a file:[/]
[green]aniworld[/] [magenta]--episode-file[/] [cyan]test.txt[/] [magenta]--language[/] [cyan]"German Dub"[/]

[bold yellow]Example 7: Use a custom provider URL[/]
[dim]Download a provider page URL directly (resolved to a direct media URL and saved via ffmpeg).[/]
[dim]Important: you must specify --provider so the right extractor (and headers) are used.[/]
[green]aniworld[/] [magenta]--provider[/] [cyan]VOE[/] [magenta]--provider-url[/] [blue]https://voe.sx/e/ayginbzzb6bi[/]

[bold]Notes[/]
- [magenta]--aniskip[/] and [magenta]--keep-watching[/] can be combined with Watch and Syncplay.
- URLs are positional arguments, so you can paste one or many at the end of the command.
""".strip()


def parse_args():
    parser = argparse.ArgumentParser(
        prog="aniworld",
        description=(
            "AniWorld Downloader is a cross-platform tool for streaming and "
            "downloading anime from aniworld.to, as well as movies and series "
            "from s.to. It runs on Windows, macOS, and Linux, providing a "
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
        help="Prefer s.to for interactive searches.",
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
        help="Specify the Syncplay room name",
    )
    syncplay.add_argument(
        "-sU",
        "--syncplay-username",
        help="Specify the Syncplay username",
    )
    syncplay.add_argument(
        "-sP",
        "--syncplay-password",
        help="Specify the Syncplay password (if required)",
    )

    args = parser.parse_args()

    if args.examples:
        console.print(
            Panel.fit(
                Text.from_markup(EXAMPLES),
                title="[bold]aniworld --examples[/bold]",
                border_style="cyan",
            )
        )
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
