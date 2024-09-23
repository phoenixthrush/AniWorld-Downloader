import subprocess
import re

from aniworld import globals as aniworld_globals
from aniworld.common import clear_screen


class Args:
    def __init__(self, **kwargs):
        self.attributes = {
            'slug': kwargs.get('slug', None),
            'link': kwargs.get('link', None),
            'query': kwargs.get('query', None),
            'episode': kwargs.get('episode', None),
            'action': kwargs.get('action', aniworld_globals.DEFAULT_ACTION),
            'output': kwargs.get('output', aniworld_globals.DEFAULT_DOWNLOAD_PATH),
            'language': kwargs.get('language', aniworld_globals.DEFAULT_LANGUAGE),
            'provider': kwargs.get('provider', aniworld_globals.DEFAULT_PROVIDER),
            'aniskip': kwargs.get('aniskip', False),
            'keep_watching': kwargs.get('keep_watching', False),
            'only_direct_link': kwargs.get('only_direct_link', False),
            'only_command': kwargs.get('only_command', False),
            'proxy': kwargs.get('proxy', None),
            'debug': kwargs.get('debug', False)
        }

    def __getattr__(self, item):
        return self.attributes.get(item)

    def __str__(self):
        return f"Args({self.attributes})"


def test_main(args):
    command = ['aniworld']
    arg_map = {
        'slug': '--slug',
        'link': '--link',
        'query': '--query',
        'episode': '--episode',
        'action': '--action',
        'output': '--output',
        'language': '--language',
        'provider': '--provider',
        'proxy': '--proxy',
        'aniskip': '--aniskip',
        'keep_watching': '--keep-watching',
        'only_direct_link': '--only-direct-link',
        'only_command': '--only-command',
        'debug': '--debug'
    }

    for arg, flag in arg_map.items():
        value = getattr(args, arg)
        if value is not None:
            if isinstance(value, bool) and value:
                command.append(flag)
            elif not isinstance(value, bool):
                command.extend([flag, value])

    try:
        result = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command '{e.cmd}' returned non-zero exit status {e.returncode}.")
        print(f"Error output: {e.stderr}")
        raise


def run_test(test_name, args, expected_pattern, first_test=False):
    try:
        if not first_test:
            print(f"\nTesting {test_name}...")
        else:
            print(f"Testing {test_name}...")
        output = test_main(args)
        assert re.search(expected_pattern, output), (
            f"Output did not contain expected pattern: {output}"
        )
        print("\033[92mOK\033[0m")
    except AssertionError:
        print("\033[91mFAILURE\033[0m")


def test_functions():
    clear_screen()
    episode = 'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1'

    run_test(
        "Download",
        Args(
            only_command=True,
            episode=episode,
            output='/Users/bleh/Downloads/Demon Slayer: Kimetsu no Yaiba - S1E1.mp4',
            language='English Sub',
            provider='Vidoza'
        ),
        r"https://[^\s]*v\.mp4[^\s]*",
        True
    )

    run_test(
        "Watch",
        Args(
            only_command=True,
            episode=episode,
            action='Watch',
            provider='VOE',
            language='German Dub'
        ),
        r"https://[^\s]*master\.m3u8[^\s]*",
        r"mpv 'https://[^\s]*master\.m3u8[^\s]*' --fs --quiet --really-quiet "
        r"'--force-media-title=Demon Slayer: Kimetsu no Yaiba - S1E1 - Grausamkeit / Cruelty'"
    )

    # TODO aniskip is not applied
    run_test(
        "Syncplay",
        Args(
            only_command=True,
            episode=episode,
            action='Syncplay',
            provider='Streamtape',
            aniskip=True
        ),
        r"https://[^\s]*streamtape\.com/get_video[^\s]*",
        r"syncplay --no-gui --no-store --host syncplay.pl:8997 --name phoenixthrush "
        r"--room Demon_Slayer:_Kimetsu_no_Yaiba_-_S1E1_-_Grausamkeit_/_Cruelty "
        r"--player-path /opt/homebrew/bin/mpv 'https://[^\s]*streamtape\.com/get_video[^\s]*' "
        r"-- --fs '--force-media-title=Demon Slayer: Kimetsu no Yaiba - "
        r"S1E1 - Grausamkeit / Cruelty'"
    )


test_functions()
