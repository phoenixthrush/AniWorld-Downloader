import platform
import getpass
import subprocess

from bs4 import BeautifulSoup

from test_extractors import make_request, providers, clear_screen, test_provider

from aniworld import doodstream_get_direct_link
from aniworld import streamtape_get_direct_link
from aniworld import vidoza_get_direct_link
from aniworld import voe_get_direct_link


def syncplay(provider_name, get_direct_link_func):
    url = "https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1"
    soup = BeautifulSoup(make_request(url), 'html.parser')
    data = providers(soup)

    clear_screen()

    direct_links = test_provider(data, provider_name, get_direct_link_func, False)
    # print("Direct Links:", direct_links)

    if 3 in direct_links:
        link = direct_links[3]  # ger sub
    else:
        print("Error: German subtitle link (3) not found in direct_links.")
        return

    if platform.system() == "Darwin":
        syncplay = "/Applications/Syncplay.app/Contents/MacOS/Syncplay"
        mpv = "/opt/homebrew/bin/mpv"
    elif platform.system() == "Windows":
        syncplay = "C:\\Program Files\\Syncplay\\Syncplay.exe"
        mpv = "C:\\Program Files\\mpv\\mpv.exe"
    else:
        syncplay = "/usr/bin/syncplay"
        mpv = "/usr/bin/mpv"

    anime_slug = "demon-slayer-kimetsu-no-yaiba"
    command = [
        syncplay,
        "--no-gui",
        "--host", "syncplay.pl:8997",
        "--name", getpass.getuser(),
        "--room", anime_slug,
        "--player-path", mpv,
        link,
        "--",
        f"--title={anime_slug}"
    ]

    subprocess.Popen(
        command,
        creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def main():
    syncplay("VOE", voe_get_direct_link)
    syncplay("Vidoza", vidoza_get_direct_link)


if __name__ == "__main__":
    main()
