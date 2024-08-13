import os
import re
import shutil
import sys
import getpass
import platform
from typing import Dict, List, Optional, Any

from bs4 import BeautifulSoup

from aniworld import (
    doodstream_get_direct_link,
    streamtape_get_direct_link,
    vidoza_get_direct_link,
    voe_get_direct_link,
    fetch_url_content,
    check_dependencies,
    aniskip,
    setup_aniskip,
    execute_command
)

"""
TODO:
    - Split into multiple functions
    - Add type and function description
"""

def providers(soup: BeautifulSoup) -> Dict[str, Dict[int, str]]:
    """
    Extracts streaming providers and their language-specific redirect links from a BeautifulSoup object.

    Args:
        soup (BeautifulSoup): A BeautifulSoup object containing the parsed HTML of a webpage.

    Returns:
        Dict[str, Dict[int, str]]: A dictionary where the keys are provider names (str) and the values are 
                                   dictionaries mapping language keys (int) to redirect links (str).
    """
    provider_options = soup.find(class_='hosterSiteVideo').find('ul', class_='row').find_all('li')

    extracted_data = {}
    for provider in provider_options:
        lang_key = int(provider.get('data-lang-key'))
        redirect_link = provider.get('data-link-target')
        provider = provider.find('h4').text.strip()

        if provider not in extracted_data:
            extracted_data[provider] = {}

        extracted_data[provider][lang_key] = f"https://aniworld.to{redirect_link}"

    return extracted_data


def build_mpv_command(link: str, mpv_title: str, aniskip_options: Optional[List[str]] = None) -> List[str]:
    """
    Builds the command to play a video using MPV.

    Args:
        link (str): The URL of the video to play.
        mpv_title (str): The title to force display in the MPV player.
        aniskip_options (Optional[List[str]]): A list of additional aniskip options to be appended to the command.

    Returns:
        List[str]: The command to run MPV with the specified options.
    """
    command = [
        "mpv",
        link,
        "--fs",
        "--quiet",
        "--really-quiet",
        f"--force-media-title={mpv_title}"
    ]
    if aniskip_options:
        command.extend(aniskip_options)
    return command


def build_yt_dlp_command(link: str, output_file: str) -> List[str]:
    """
    Builds the command to download a video using yt-dlp.

    Args:
        link (str): The URL of the video to download.
        output_file (str): The file path where the downloaded video will be saved.

    Returns:
        List[str]: The command to run yt-dlp with the specified options.
    """
    return [
        "yt-dlp",
        "--fragment-retries", "infinite",
        "--concurrent-fragments", "4",
        "-o", output_file,
        "--quiet",
        "--progress",
        "--no-warnings",
        link
    ]


def build_syncplay_command(link: str, mpv_title: str, aniskip_options: Optional[List[str]] = None) -> List[str]:
    """
    Builds the command to play a video using Syncplay.

    Args:
        link (str): The URL of the video to play.
        mpv_title (str): The title to force display in the MPV player.
        aniskip_options (Optional[List[str]]): A list of additional aniskip options to be appended to the command.

    Returns:
        List[str]: The command to run Syncplay with the specified options.
    """
    syncplay = "SyncplayConsole" if platform.system() == "Windows" else "syncplay"
    command = [
        syncplay,
        "--no-gui",
        "--host", "syncplay.pl:8997",
        "--name", getpass.getuser(),
        "--room", mpv_title,
        "--player-path", shutil.which("mpv"),
        link,
        "--", "--fs",
        "--", f"--force-media-title={mpv_title}"
    ]
    if aniskip_options:
        command.extend(aniskip_options)
    return command


def process_aniskip(anime_title: str, season_number: int, episode_number: int) -> List[str]:
    """
    Processes aniskip options for a given anime episode.

    Args:
        anime_title (str): The title of the anime.
        episode_number (int): The episode number.
        season_number (int): The season number.

    Returns:
        List[str]: A list of aniskip options formatted for command line use.
    """

    if season_number != 1:
        print("Warning: This is not season 1."
              "Aniskip timestamps might be incorrect."
              "This issue will be fixed in the future.")

    skip_options = aniskip(anime_title, episode_number)
    skip_options_list = skip_options.split(' --')
    return [
        f"--{opt}" if not opt.startswith('--') else opt
        for opt in skip_options_list
    ]


def main(params: Dict[str, Any]) -> None:
    """
    Main function to handle different actions (Watch, Download, Syncplay).

    Args:
        params (Dict[str, Any]): Dictionary containing all parameters. Keys include:
            - action (str): The action to perform ("Watch", "Download", "Syncplay").
            - link (str): The video link.
            - mpv_title (str): The title to be displayed in the media player.
            - anime_title (str): The title of the anime.
            - episode_number (int): The episode number.
            - season_number (int): The season number.
            - output_directory (str): Directory to save downloaded files.
            - only_command (bool, optional): If True, only prints the command. Defaults to False.
            - aniskip_selected (bool, optional): If True, processes aniskip options. Defaults to False.
    """
    action = params.get("action")
    link = params.get("link")
    mpv_title = params.get("mpv_title")
    anime_title = params.get("anime_title")
    episode_number = params.get("episode_number")
    season_number = params.get("season_number")
    output_directory = params.get("output_directory")
    only_command = params.get("only_command", False)
    aniskip_selected = params.get("aniskip_selected", False)

    if action == "Watch":
        check_dependencies(["mpv"])
        if not only_command:
            print(f"Playing '{mpv_title}'")

        aniskip_options = None
        if aniskip_selected:
            aniskip_options = process_aniskip(anime_title,season_number, episode_number)

        command = build_mpv_command(link, mpv_title, aniskip_options)
        execute_command(command, only_command)

    elif action == "Download":
        check_dependencies(["yt-dlp"])
        file_name = f"{mpv_title}.mp4"
        file_path = os.path.join(output_directory, file_name)
        if not only_command:
            print(f"Downloading to '{file_path}'")

        command = build_yt_dlp_command(link, file_path)
        execute_command(command, only_command)

    elif action == "Syncplay":
        check_dependencies(["syncplay"])
        aniskip_options = None
        if aniskip_selected:
            aniskip_options = process_aniskip(anime_title, season_number, episode_number)

        command = build_syncplay_command(link, mpv_title, aniskip_options)
        execute_command(command, only_command)


def execute(
    selected_episodes: list,
    provider_selected,
    action_selected,
    aniskip_selected,
    lang,
    output_directory,
    anime_title,
    only_direct_link=False,
    only_command=False,
    debug=False
):
    for episode_url in selected_episodes:
        episode_html = fetch_url_content(episode_url)
        if episode_html is None:
            continue
        soup = BeautifulSoup(episode_html, 'html.parser')

        if debug:
            print(f"Episode Soup: {soup.prettify}")

        episodeGermanTitle = soup.find('span', class_='episodeGermanTitle').text
        episodeEnglishTitle = soup.find('small', class_='episodeEnglishTitle').text
        episode_title = f"{episodeGermanTitle} / {episodeEnglishTitle}"

        anime_title = soup.find('div', class_='hostSeriesTitle').text

        if debug:
            print(f"Episode Title: {episode_title}")

        data = providers(soup)

        if debug:
            print(f"Provider Data: {data}")

        provider_mapping = {
            "Vidoza": vidoza_get_direct_link,
            "VOE": voe_get_direct_link,
            "Doodstream": doodstream_get_direct_link,
            "Streamtape": streamtape_get_direct_link
        }

        if provider_selected in data:
            for language in data[provider_selected]:
                if language == int(lang):
                    matches = re.findall(r'\d+', episode_url)
                    season_number = int(matches[-2])
                    episode_number = int(matches[-1])

                    action = action_selected

                    if aniskip_selected:
                        setup_aniskip()

                    provider_function = provider_mapping[provider_selected]
                    request_url = data[provider_selected][language]
                    html_content = fetch_url_content(request_url)
                    soup = BeautifulSoup(html_content, 'html.parser')

                    if debug:
                        print(f"Episode Data: {soup.prettify}")

                    link = provider_function(soup)

                    if only_direct_link:
                        print(link)
                        sys.exit()

                    mpv_title = f"{anime_title} S{season_number}E{episode_number} - {episode_title}"

                    params = {
                        "action": action,
                        "link": link,
                        "mpv_title": mpv_title,
                        "anime_title": anime_title,
                        "episode_number": episode_number,
                        "season_number": season_number,
                        "output_directory": output_directory,
                        "only_command": only_command,
                        "aniskip_selected": aniskip_selected
                    }

                    main(params=params)