import os
import re
import shutil
import sys
import getpass
import platform
from typing import Dict, List, Optional, Any

from bs4 import BeautifulSoup

from aniworld.extractors import (
    doodstream_get_direct_link,
    streamtape_get_direct_link,
    vidoza_get_direct_link,
    voe_get_direct_link,
)

from aniworld.common import (
    clean_up_leftovers,
    execute_command,
    setup_aniskip,
    fetch_url_content,
    check_dependencies
)

from aniworld.aniskip import aniskip

def providers(soup: BeautifulSoup) -> Dict[str, Dict[int, str]]:
    """
    Extracts streaming providers and their language-specific redirect links
    from the BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object containing the HTML content of the page.

    Returns:
        Dict[str, Dict[int, str]]: A dictionary where the keys are provider names
        and the values are dictionaries
        mapping language keys to redirect links.
    """
    provider_options = soup.find(class_='hosterSiteVideo').find('ul', class_='row').find_all('li')
    extracted_data = {}
    for provider in provider_options:
        lang_key = int(provider.get('data-lang-key'))
        redirect_link = provider.get('data-link-target')
        provider_name = provider.find('h4').text.strip()
        if provider_name not in extracted_data:
            extracted_data[provider_name] = {}
        extracted_data[provider_name][lang_key] = f"https://aniworld.to{redirect_link}"
    return extracted_data


def build_mpv_command(
    link: str, mpv_title: str, aniskip_options: Optional[List[str]] = None
) -> List[str]:
    """
    Constructs the command for playing the video with MPV.

    Args:
        link (str): The URL of the video.
        mpv_title (str): The title to be displayed in MPV.
        aniskip_options (Optional[List[str]]): Additional options for aniskip, if any.

    Returns:
        List[str]: The command to be executed.
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
    Constructs the command for downloading the video with yt-dlp.

    Args:
        link (str): The URL of the video.
        output_file (str): The path to the output file.

    Returns:
        List[str]: The command to be executed.
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


def build_syncplay_command(
    link: str, mpv_title: str, aniskip_options: Optional[List[str]] = None
) -> List[str]:
    """
    Constructs the command for syncing playback with Syncplay.

    Args:
        link (str): The URL of the video.
        mpv_title (str): The title to be displayed in Syncplay.
        aniskip_options (Optional[List[str]]): Additional options for aniskip, if any.

    Returns:
        List[str]: The command to be executed.
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
        season_number (int): The season number of the episode.
        episode_number (int): The episode number.

    Returns:
        List[str]: A list of aniskip options formatted as command-line arguments.
    """
    if season_number != 1:
        print("Warning: This is not season 1. Aniskip timestamps might be incorrect."
              "This issue will be fixed in the future.")
    skip_options = aniskip(anime_title, episode_number)
    skip_options_list = skip_options.split(' --')
    return [f"--{opt}" if not opt.startswith('--') else opt for opt in skip_options_list]


def get_episode_title(soup: BeautifulSoup, debug: bool = False) -> str:
    """
    Retrieves the episode title from the BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object containing the HTML content of the page.
        debug (bool): Whether to print debug information.

    Returns:
        str: The formatted episode title.
    """
    german_title_tag = soup.find('span', class_='episodeGermanTitle')
    english_title_tag = soup.find('small', class_='episodeEnglishTitle')
    
    episode_german_title = german_title_tag.text if german_title_tag else None
    episode_english_title = english_title_tag.text if english_title_tag else None

    if episode_german_title:
        episode_title = f"{episode_german_title} / {episode_english_title}" if episode_english_title else episode_german_title
    else:
        episode_title = episode_english_title

    if debug:
        print(f"Episode Title: {episode_title}")

    return episode_title


def get_anime_title(soup: BeautifulSoup) -> str:
    """
    Retrieves the anime title from the BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object containing the HTML content of the page.

    Returns:
        str: The anime title.
    """
    return soup.find('div', class_='hostSeriesTitle').text


def get_provider_data(soup: BeautifulSoup, debug: bool = False) -> Dict[str, Dict[int, str]]:
    """
    Retrieves provider data from the BeautifulSoup object.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object containing the HTML content of the page.
        debug (bool): Whether to print debug information.

    Returns:
        Dict[str, Dict[int, str]]: A dictionary with provider names as keys
        and dictionaries of language-specific
        links as values.
    """
    data = providers(soup)
    if debug:
        print(f"Provider Data: {data}")
    return data


def get_season_and_episode_numbers(episode_url: str) -> tuple:
    """
    Extracts the season and episode numbers from the episode URL.

    Args:
        episode_url (str): The URL of the episode.

    Returns:
        tuple: A tuple containing the season number and episode number.
    """
    matches = re.findall(r'\d+', episode_url)
    season_number = int(matches[-2])
    episode_number = int(matches[-1])
    return season_number, episode_number


def fetch_direct_link(provider_function, request_url: str, debug: bool = False) -> str:
    """
    Fetches the direct link using the provided provider function.

    Args:
        provider_function: The function to be used to fetch the direct link.
        request_url (str): The URL to request.
        debug (bool): Whether to print debug information.

    Returns:
        str: The fetched direct link.
    """
    html_content = fetch_url_content(request_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    if debug:
        print(f"Episode Data: {soup.prettify()}")
    return provider_function(soup)


def perform_action(params: Dict[str, Any]) -> None:
    """
    Performs the specified action (Watch, Download, Syncplay) based on the provided parameters.

    Args:
        params (Dict[str, Any]): A dictionary containing action parameters.

    Returns:
        None
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

    aniskip_options = (
        process_aniskip(anime_title, season_number, episode_number)
        if aniskip_selected
        else None
    )

    if action == "Watch":
        mpv_title = mpv_title.replace(" --- ", " - ", 1)
        check_dependencies(["mpv"])
        setup_aniskip()
        if not only_command:
            print(f"Playing '{mpv_title}'")
        command = build_mpv_command(link, mpv_title, aniskip_options)
        execute_command(command, only_command)
    elif action == "Download":
        check_dependencies(["yt-dlp"])
        file_name = f"{mpv_title}.mp4".replace("/", "-")
        file_path = os.path.join(output_directory, file_name).replace(" --- ", "/", 1)
        if not only_command:
            print(f"Downloading to '{file_path}'")
        command = build_yt_dlp_command(link, file_path)
        try:
            execute_command(command, only_command)
        except KeyboardInterrupt:
            clean_up_leftovers(os.path.dirname(file_path))
    elif action == "Syncplay":
        mpv_title = mpv_title.replace(" --- ", " - ", 1)
        check_dependencies(["mpv", "syncplay"])
        setup_aniskip()
        if not only_command:
            print(f"Playing '{mpv_title}'")
        command = build_syncplay_command(link, mpv_title, aniskip_options)
        execute_command(command, only_command)


def execute(params: Dict[str, Any]) -> None:
    """
    Processes selected episodes based on the provided parameters.
    This function handles fetching episode content,
    extracting relevant information, and performing the specified actions
    (Watch, Download, Syncplay).

    Args:
        params (Dict[str, Any]): A dictionary containing the following keys:
            - 'selected_episodes': List of URLs for the episodes to process.
            - 'provider_selected': The name of the provider to use (e.g., "Vidoza").
            - 'action_selected': The action to perform (e.g., "Watch", "Download", "Syncplay").
            - 'aniskip_selected': A boolean indicating whether aniskip should be used.
            - 'lang': The language code to use for the provider.
            - 'output_directory': Directory where files should be saved (for download action).
            - 'anime_title': The title of the anime.
            - 'only_direct_link': A boolean indicating if only the direct link should be printed.
            - 'only_command': A boolean indicating if only the command should be executed.
            - 'debug': A boolean indicating if debug information should be printed.
    """
    provider_mapping = {
        "Vidoza": vidoza_get_direct_link,
        "VOE": voe_get_direct_link,
        "Doodstream": doodstream_get_direct_link,
        "Streamtape": streamtape_get_direct_link
    }

    selected_episodes = params['selected_episodes']
    provider_selected = params['provider_selected']
    action_selected = params['action_selected']
    aniskip_selected = params['aniskip_selected']
    lang = params['lang']
    output_directory = params['output_directory']
    anime_title = params['anime_title']
    only_direct_link = params.get('only_direct_link', False)
    only_command = params.get('only_command', False)
    debug = params.get('debug', False)

    for episode_url in selected_episodes:
        episode_html = fetch_url_content(episode_url)
        if episode_html is None:
            continue
        soup = BeautifulSoup(episode_html, 'html.parser')

        episode_title = get_episode_title(soup, debug)
        anime_title = get_anime_title(soup)
        data = get_provider_data(soup, debug)

        if provider_selected in data:
            for language in data[provider_selected]:
                if language == int(lang):
                    season_number, episode_number = get_season_and_episode_numbers(episode_url)
                    action = action_selected

                    provider_function = provider_mapping[provider_selected]
                    request_url = data[provider_selected][language]
                    link = fetch_direct_link(provider_function, request_url, debug)

                    if only_direct_link:
                        print(link)
                        sys.exit()

                    mpv_title = f"{anime_title} --- S{season_number}E{episode_number} - {episode_title}"

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

                    perform_action(params)
