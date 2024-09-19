import subprocess
import re

from aniworld import globals
from aniworld.common import clear_screen

class Args:
    def __init__(self, **kwargs):
        self.slug = kwargs.get('slug', None)
        self.link = kwargs.get('link', None)
        self.query = kwargs.get('query', None)
        self.episode = kwargs.get('episode', None)
        self.action = kwargs.get('action', globals.DEFAULT_ACTION)
        self.output = kwargs.get('output', globals.DEFAULT_DOWNLOAD_PATH)
        self.language = kwargs.get('language', globals.DEFAULT_LANGUAGE)
        self.provider = kwargs.get('provider', globals.DEFAULT_PROVIDER)
        self.aniskip = kwargs.get('aniskip', False)
        self.keep_watching = kwargs.get('keep_watching', False)
        self.only_direct_link = kwargs.get('only_direct_link', False)
        self.only_command = kwargs.get('only_command', False)
        self.proxy = kwargs.get('proxy', None)
        self.debug = kwargs.get('debug', False)

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
        'proxy': '--proxy'
    }
    for arg, flag in arg_map.items():
        value = getattr(args, arg)
        if value is not None:
            command.extend([flag, value])
    
    flag_map = {
        'aniskip': '--aniskip',
        'keep_watching': '--keep-watching',
        'only_direct_link': '--only-direct-link',
        'only_command': '--only-command',
        'debug': '--debug'
    }
    for arg, flag in flag_map.items():
        if getattr(args, arg):
            command.append(flag)

    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command '{e.cmd}' returned non-zero exit status {e.returncode}.")
        print(f"Error output: {e.stderr}")
        raise

def test_functions():
    clear_screen()
    episode = 'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1'

    print("Testing Download...")
    test_args_1 = Args(only_command=True, episode=episode, output='/Users/bleh/Downloads/Demon Slayer: Kimetsu no Yaiba - S1E1.mp4', language='English Sub')
    output_1 = test_main(test_args_1)
    url_pattern = r"https://[^\s]*v\.mp4[^\s]*"
    expected_pattern = rf"yt-dlp --fragment-retries infinite --concurrent-fragments 4 -o '/Users/bleh/Downloads/Demon Slayer: Kimetsu no Yaiba - S1E1.mp4/Demon Slayer: Kimetsu no Yaiba - S1E1.mp4' --quiet --progress --no-warnings {url_pattern}"
    assert re.search(expected_pattern, output_1), f"Output did not contain expected pattern: {output_1}"
    print("\033[92mOK\033[0m")

    print("\nTesting Watch...")
    test_args_1 = Args(only_command=True, episode=episode, action='Watch', provider='VOE', language='German Dub')
    output_1 = test_main(test_args_1)
    url_pattern = r"https://[^\s]*master\.m3u8[^\s]*"
    expected_pattern = rf"mpv '{url_pattern}' --fs --quiet --really-quiet '--force-media-title=Demon Slayer: Kimetsu no Yaiba - S1E1 - Grausamkeit / Cruelty'"
    assert re.search(expected_pattern, output_1), f"Output did not contain expected pattern: {output_1}"
    print("\033[92mOK\033[0m")

    print("\nTesting Syncplay...")
    test_args_1 = Args(only_command=True, episode=episode, action='Syncplay', provider='Streamtape', aniskip=True)
    output_1 = test_main(test_args_1)
    url_pattern = r"https://[^\s]*streamtape\.com/get_video[^\s]*"
    expected_pattern = rf"syncplay --no-gui --no-store --host syncplay.pl:8997 --name phoenixthrush --room Demon_Slayer:_Kimetsu_no_Yaiba_-_S1E1_-_Grausamkeit_/_Cruelty --player-path /opt/homebrew/bin/mpv '{url_pattern}' -- --fs '--force-media-title=Demon Slayer: Kimetsu no Yaiba - S1E1 - Grausamkeit / Cruelty'"
    assert re.search(expected_pattern, output_1), f"Output did not contain expected pattern: {output_1}"
    print("\033[92mOK\033[0m")

test_functions()