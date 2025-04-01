import sys
import argparse
import platform
import logging
import subprocess

from aniworld.config import (
    DEFAULT_ACTION,
    DEFAULT_PROVIDER_DOWNLOAD,
    DEFAULT_PROVIDER_WATCH,
    DEFAULT_LANGUAGE,
    VERSION,
    SUPPORTED_PROVIDERS
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse command-line arguments for anime streaming, "
                    "downloading, and playback management."
    )

    # General options
    general_opts = parser.add_argument_group('General Options')
    general_opts.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug mode for detailed logs.'
    )
    general_opts.add_argument(
        '-U', '--update',
        type=str,
        choices=['mpv', 'yt-dlp', 'syncplay', 'all'],
        help='Update specified tools (mpv, yt-dlp, syncplay, or all).'
    )
    general_opts.add_argument(
        '-u', '--uninstall',
        action='store_true',
        help='Perform self-uninstallation.'
    )
    general_opts.add_argument(
        '-v', '--version',
        action='store_true',
        help='Display version information.'
    )

    # Search options
    search_opts = parser.add_argument_group('Search Options')
    search_opts.add_argument(
        '-l', '--link',
        type=str,
        help='Provide a direct link (e.g., https://aniworld.to/anime/stream/...).'
    )
    search_opts.add_argument(
        '-s', '--slug',
        type=str,
        help='Specify a search slug (e.g., demon-slayer-kimetsu-no-yaiba).'
    )
    search_opts.add_argument(
        '-q', '--query',
        type=str,
        help='Enter a search query (e.g., demon).'
    )

    # Episode options
    episode_opts = parser.add_argument_group('Episode Options')
    episode_opts.add_argument(
        '-e', '--episode',
        type=str,
        nargs='+',
        help='Specify one or more episode URLs.'
    )
    episode_opts.add_argument(
        '-f', '--episode-file',
        type=str,
        help='Provide a file containing episode URLs.'
    )
    episode_opts.add_argument(
        '-lf', '--local-episodes',
        action='store_true',
        help='Use local MP4 files for episodes instead of URLs.'
    )

    # Action options
    action_opts = parser.add_argument_group('Action Options')
    action_opts.add_argument(
        '-a', '--action',
        type=str,
        choices=['Watch', 'Download', 'Syncplay'],
        default=DEFAULT_ACTION,
        help='Specify the action to perform.'
    )
    action_opts.add_argument(
        '-o', '--output-dir',
        type=str,
        help='Set the download directory (e.g., /path/to/downloads).'
    )
    action_opts.add_argument(
        '-O', '--final-dir',
        type=str,
        help='Set the final download directory (defaults to anime name if not specified).'
    )
    action_opts.add_argument(
        '-L', '--language',
        type=str,
        choices=['German Dub', 'English Sub', 'German Sub'],
        default=DEFAULT_LANGUAGE,
        help='Specify the language for playback or download.'
    )
    action_opts.add_argument(
        '-p', '--provider',
        type=str,
        choices=SUPPORTED_PROVIDERS,
        help='Specify the preferred provider.'
    )

    # Anime4K options
    anime4k_opts = parser.add_argument_group('Anime4K Options')
    anime4k_opts.add_argument(
        '-A', '--anime4k',
        type=str,
        choices=['High', 'Low', 'Remove'],
        help='Set Anime4K mode (High, Low, or Remove for performance tuning).'
    )

    # Syncplay options
    syncplay_opts = parser.add_argument_group('Syncplay Options')
    syncplay_opts.add_argument(
        '-sH', '--hostname',
        type=str,
        help='Set the Syncplay server hostname.'
    )
    syncplay_opts.add_argument(
        '-sU', '--username',
        type=str,
        help='Set the Syncplay username.'
    )
    syncplay_opts.add_argument(
        '-sR', '--room',
        type=str,
        help='Specify the Syncplay room name.'
    )
    syncplay_opts.add_argument(
        '-sP', '--password',
        type=str,
        nargs='+',
        help='Set the Syncplay room password.'
    )

    # Miscellaneous options
    misc_opts = parser.add_argument_group('Miscellaneous Options')
    misc_opts.add_argument(
        '-k', '--aniskip',
        action='store_true',
        help='Skip anime intros and outros using Aniskip.'
    )
    misc_opts.add_argument(
        '-K', '--keep-watching',
        action='store_true',
        help='Automatically continue to the next episodes after the selected one.'
    )
    misc_opts.add_argument(
        '-r', '--random',
        type=str,
        nargs='?',
        const="all",
        help='Play a random anime (default genre is "all", e.g., Drama).'
    )
    misc_opts.add_argument(
        '-D', '--only-direct-link',
        action='store_true',
        help='Output only the direct streaming link.'
    )
    misc_opts.add_argument(
        '-C', '--only-command',
        action='store_true',
        help='Output only the execution command.'
    )

    args = parser.parse_args()

    if args.version:
        cowsay = fR"""
_____________________________
< AniWorld-Downloader {VERSION} >
-----------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
"""
        print(cowsay.strip())
        sys.exit()

    if args.action is None:
        args.action = "Download"

    if args.provider is None:
        if args.action == "Download":
            args.provider = DEFAULT_PROVIDER_DOWNLOAD
        else:
            args.provider = DEFAULT_PROVIDER_WATCH

    if args.debug is True:
        def open_terminal_with_command(command):
            terminal_emulators = [
                ('gnome-terminal', ['gnome-terminal', '--',
                 'bash', '-c', f'{command}; exec bash']),
                ('xterm', ['xterm', '-hold', '-e', command]),
                ('konsole', ['konsole', '--hold', '-e', command])
            ]

            for terminal, cmd in terminal_emulators:
                try:
                    subprocess.Popen(
                        cmd)  # pylint: disable=consider-using-with
                    return
                except FileNotFoundError:
                    logging.debug(
                        "%s not found, trying next option.", terminal)
                except subprocess.SubprocessError as e:
                    logging.error(
                        "Error opening terminal with %s: %s", terminal, e)

            logging.error(
                "No supported terminal emulator found. Install gnome-terminal, xterm, or konsole.")

        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("============================================")
        logging.debug("Welcome to Aniworld!")
        logging.debug("============================================\n")
        logging.debug("Debug mode enabled")

        system = platform.system()

        if system == "Darwin":
            try:
                subprocess.run([
                    "osascript", "-e",
                    'tell application "Terminal" to do script "trap exit SIGINT; tail -f -n +1 $TMPDIR/aniworld.log" activate'
                ], check=True)
                logging.debug(
                    "Started tailing the log file in a new Terminal window.")
            except subprocess.CalledProcessError as e:
                logging.error("Failed to start tailing the log file: %s", e)
        elif system == "Windows":
            try:
                command = (
                    "start cmd /c \"powershell -NoExit -c Get-Content -Wait \"$env:TEMP\\aniworld.log\"\""
                )
                subprocess.run(command, shell=True, check=True)
                logging.debug(
                    "Started tailing the log file in a new Terminal window.")
            except subprocess.CalledProcessError as e:
                logging.error("Failed to start tailing the log file: %s", e)
        elif system == "Linux":
            open_terminal_with_command('tail -f -n +1 /tmp/aniworld.log')

    return parser.parse_args()


arguments = parse_arguments()
