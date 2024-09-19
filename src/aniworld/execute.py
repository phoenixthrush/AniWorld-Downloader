import os
import re
import shutil
import getpass
import platform
from typing import Dict, List, Optional, Any
import logging

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
    check_dependencies,
    get_language_string
)

from aniworld.aniskip import aniskip

def providers(soup: BeautifulSoup) -> Dict[str, Dict[int, str]]:
    logging.debug("Extracting provider data from soup")
    provider_options = soup.find(class_='hosterSiteVideo').find('ul', class_='row').find_all('li')
    extracted_data = {}
    for provider in provider_options:
        lang_key = int(provider.get('data-lang-key'))
        redirect_link = provider.get('data-link-target')
        provider_name = provider.find('h4').text.strip()
        if provider_name not in extracted_data:
            extracted_data[provider_name] = {}
        extracted_data[provider_name][lang_key] = f"https://aniworld.to{redirect_link}"
    logging.debug(f"Extracted provider data: {extracted_data}")
    return extracted_data

def build_command(
    link: str, mpv_title: str, player: str, aniskip_selected: bool, aniskip_options: Optional[List[str]] = None
) -> List[str]:
    logging.debug(f"Building command for mpv with link: {link}, title: {mpv_title}, player: {player}, aniskip_selected: {aniskip_selected}, aniskip_options: {aniskip_options}")
    command = [
        player,
        link,
        "--fs",
        "--quiet",
        "--really-quiet",
        f"--force-media-title={mpv_title}"
    ]

    if aniskip_selected:
        logging.debug("Aniskip selected, setting up aniskip")
        setup_aniskip()
        if aniskip_options:
            logging.debug(f"Adding aniskip options: {aniskip_options}")
            command.extend(aniskip_options)

    logging.debug(f"Built command: {command}")
    return command

def build_yt_dlp_command(link: str, output_file: str) -> List[str]:
    logging.debug(f"Building yt-dlp command with link: {link}, output_file: {output_file}")
    command = [
        "yt-dlp",
        "--fragment-retries", "infinite",
        "--concurrent-fragments", "4",
        "-o", output_file,
        "--quiet",
        "--progress",
        "--no-warnings",
        link
    ]
    logging.debug(f"Built yt-dlp command: {command}")
    return command

def process_aniskip(anime_title: str, season_number: int, episode_number: int) -> List[str]:
    logging.debug(f"Processing aniskip for {anime_title}, season {season_number}, episode {episode_number}")
    if season_number != 1:
        logging.debug("Aniskip is disabled for seasons other than 1.")
        return []
    skip_options = aniskip(anime_title, episode_number)
    skip_options_list = skip_options.split(' --')
    processed_options = [f"--{opt}" if not opt.startswith('--') else opt for opt in skip_options_list]
    logging.debug(f"Processed aniskip options: {processed_options}")
    return processed_options

def get_episode_title(soup: BeautifulSoup) -> str:
    logging.debug("Getting episode title from soup")
    german_title_tag = soup.find('span', class_='episodeGermanTitle')
    english_title_tag = soup.find('small', class_='episodeEnglishTitle')
    
    episode_german_title = german_title_tag.text if german_title_tag else None
    episode_english_title = english_title_tag.text if english_title_tag else None

    episode_title = f"{episode_german_title} / {episode_english_title}" if episode_german_title and episode_english_title else episode_german_title or episode_english_title

    logging.debug(f"Episode title: {episode_title}")
    return episode_title

def get_anime_title(soup: BeautifulSoup) -> str:
    logging.debug("Getting anime title from soup")
    anime_title = soup.find('div', class_='hostSeriesTitle').text
    logging.debug(f"Anime title: {anime_title}")
    return anime_title

def get_provider_data(soup: BeautifulSoup) -> Dict[str, Dict[int, str]]:
    logging.debug("Getting provider data from soup")
    data = providers(soup)
    logging.debug(f"Provider data: {data}")
    return data

def get_season_and_episode_numbers(episode_url: str) -> tuple:
    logging.debug(f"Extracting season and episode numbers from URL: {episode_url}")
    matches = re.findall(r'\d+', episode_url)
    season_episode = int(matches[-2]), int(matches[-1])
    logging.debug(f"Extracted season and episode numbers: {season_episode}")
    return season_episode

def fetch_direct_link(provider_function, request_url: str) -> str:
    logging.debug(f"Fetching direct link from URL: {request_url}")
    html_content = fetch_url_content(request_url)
    soup = BeautifulSoup(html_content, 'html.parser')
    direct_link = provider_function(soup)
    logging.debug(f"Fetched direct link: {direct_link}")
    return direct_link

def build_syncplay_command(
    link: str, mpv_title: str, aniskip_options: Optional[List[str]] = None
) -> List[str]:
    logging.debug(f"Building syncplay command with link: {link}, title: {mpv_title}, aniskip_options: {aniskip_options}")
    syncplay = "SyncplayConsole" if platform.system() == "Windows" else "syncplay"
    command = [
        syncplay,
        "--no-gui",
        "--no-store",
        "--host", "syncplay.pl:8997",
        "--name", getpass.getuser(),
        "--room", mpv_title.replace(" ", "_"),
        "--player-path", shutil.which("mpv"),
        link,
        "--",
        "--fs",
        f"--force-media-title={mpv_title}"
    ]
    if aniskip_options:
        logging.debug("Aniskip options provided, setting up aniskip")
        setup_aniskip()
        command.extend(aniskip_options)

    command.extend("")
    logging.debug(f"Built syncplay command: {command}")
    return command

def perform_action(params: Dict[str, Any]) -> None:
    logging.debug(f"Performing action with params: {params}")
    action = params.get("action")
    link = params.get("link")
    mpv_title = params.get("mpv_title")
    anime_title = params.get("anime_title")
    episode_number = params.get("episode_number")
    season_number = params.get("season_number")
    output_directory = params.get("output_directory")
    only_command = params.get("only_command", False)
    aniskip_selected = bool(params.get("aniskip_selected", False))

    logging.debug(f"aniskip_selected: {aniskip_selected}")

    if aniskip_selected:
        logging.debug("Aniskip is selected, processing aniskip options")
        aniskip_options = process_aniskip(anime_title, season_number, episode_number)
        logging.debug(f"Aniskip options: {aniskip_options}")
    else:
        logging.debug("Aniskip is not selected, skipping aniskip options")
        aniskip_options = []

    if action == "Watch":
        logging.debug("Action is Watch")
        mpv_title = mpv_title.replace(" --- ", " - ", 1)
        check_dependencies(["mpv"])
        if not only_command:
            print(f"Playing '{mpv_title}'")
        command = build_command(link, mpv_title, "mpv", aniskip_selected, aniskip_options)
        logging.debug(f"Executing command: {command}")
        execute_command(command, only_command)
        logging.debug("MPV has finished.\nBye bye!")
    elif action == "Download":
        logging.debug("Action is Download")
        check_dependencies(["yt-dlp"])
        file_name = f"{anime_title} - S{season_number}E{episode_number}.mp4"
        file_path = os.path.join(output_directory, file_name).replace(" --- ", "/", 1)
        if not only_command:
            print(f"Downloading to '{file_path}'")
        command = build_yt_dlp_command(link, file_path)
        logging.debug(f"Executing command: {command}")
        try:
            execute_command(command, only_command)
        except KeyboardInterrupt:
            logging.debug("KeyboardInterrupt encountered, cleaning up leftovers")
            clean_up_leftovers(os.path.dirname(file_path))
        logging.debug("yt-dlp has finished.\nBye bye!")
    elif action == "Syncplay":
        logging.debug("Action is Syncplay")
        mpv_title = mpv_title.replace(" --- ", " - ", 1)
        check_dependencies(["mpv", "syncplay"])
        if not only_command:
            print(f"Playing '{mpv_title}'")
        command = build_syncplay_command(link, mpv_title, aniskip_options)
        logging.debug(f"Executing command: {command}")
        execute_command(command, only_command)
        logging.debug("Syncplay has finished.\nBye bye!")

def execute(params: Dict[str, Any]) -> None:
    logging.debug(f"Executing with params: {params}")
    provider_mapping = {
        "Vidoza": vidoza_get_direct_link,
        "VOE": voe_get_direct_link,
        "Doodstream": doodstream_get_direct_link,
        "Streamtape": streamtape_get_direct_link
    }

    selected_episodes = params['selected_episodes']
    action_selected = params['action_selected']
    aniskip_selected = bool(params.get("aniskip_selected", False))
    lang = params['lang']
    output_directory = params['output_directory']
    anime_title = params['anime_title']
    only_direct_link = params.get('only_direct_link', False)
    only_command = params.get('only_command', False)
    provider_selected = params['provider_selected']

    logging.debug(f"aniskip_selected: {aniskip_selected}")

    for episode_url in selected_episodes:
        logging.debug(f"Fetching episode HTML for URL: {episode_url}")
        episode_html = fetch_url_content(episode_url)
        if episode_html is None:
            logging.debug(f"No HTML content fetched for URL: {episode_url}")
            continue
        soup = BeautifulSoup(episode_html, 'html.parser')

        episode_title = get_episode_title(soup)
        anime_title = get_anime_title(soup)
        data = get_provider_data(soup)

        logging.debug(f"Language Code: {lang}")
        logging.debug(f"Available Providers: {data.keys()}")

        providers_to_try = [provider_selected] + [p for p in provider_mapping.keys() if p != provider_selected]
        for provider in providers_to_try:
            if provider in data:
                logging.debug(f"Trying provider: {provider}")
                logging.debug(f"Available Languages for {provider}: {data.get(provider, {}).keys()}")

                for language in data[provider]:
                    if language == int(lang):
                        season_number, episode_number = get_season_and_episode_numbers(episode_url)
                        action = action_selected

                        provider_function = provider_mapping[provider]
                        request_url = data[provider][language]
                        link = fetch_direct_link(provider_function, request_url)

                        if only_direct_link:
                            logging.debug(f"Only direct link requested: {link}")
                            print(link)
                            continue

                        mpv_title = f"{anime_title} --- S{season_number}E{episode_number} - {episode_title}"

                        episode_params = {
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

                        logging.debug(f"Performing action with params: {episode_params}")
                        perform_action(episode_params)
                        break
                else:
                    available_languages = [get_language_string(lang_code) for lang_code in data[provider].keys()]
                    logging.critical(f"No available languages for provider {provider} matching the selected language {get_language_string(int(lang))}. Available languages: {available_languages}")
                break
            else:
                logging.warning(f"Provider {provider} not available, trying next provider.")
        else:
            logging.error(f"Provider {provider_selected} not found in available providers.")
