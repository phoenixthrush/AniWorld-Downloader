import json
import re
import tempfile
from typing import Dict
import logging
from bs4 import BeautifulSoup
import requests
import aniworld.globals as aniworld_globals
from aniworld.common import raise_runtime_error, ftoi, get_season_episode_count, fetch_url_content

CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def fetch_ID(anime_title, season):
    ID = None

    logging.debug("Fetching MAL ID for: %s", anime_title)

    name = re.sub(r' \(\d+ episodes\)', '', anime_title)
    logging.debug("Processed name: %s", name)
    keyword = re.sub(r'\s+', '%20', name)
    logging.debug("Keyword for search: %s", keyword)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
        timeout=10
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        logging.debug("Failed to fetch MyAnimeList data.")

    mal_metadata = response.json()
    logging.debug("MAL metadata: %s", json.dumps(mal_metadata, indent=2))
    results = [entry['name'] for entry in mal_metadata['categories'][0]['items']]
    logging.debug("Results: %s", results)

    filtered_choices = [choice for choice in results if 'OVA' not in choice]
    logging.debug("Filtered choices: %s", filtered_choices)
    best_match = filtered_choices[0]
    logging.debug("Best match: %s", best_match)

    if best_match:
        for entry in mal_metadata['categories'][0]['items']:
            if entry['name'] == best_match:
                logging.debug("Found MAL ID: %s for %s", entry['id'], best_match)
                logging.debug(entry['id'])
                ID = entry['id']


    while season > 1:
        url = f"https://myanimelist.net/anime/{ID}"

        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        sequel_div = soup.find("div", string=lambda text: text and "Sequel" in text and "(TV)" in text)

        if sequel_div:
            title_div = sequel_div.find_next("div", class_="title")
            if title_div:
                link_element = title_div.find("a")
                if link_element:
                    link_url = link_element.get("href")
                    logging.debug("Found Link:", link_url)
                    match = re.search(r'/anime/(\d+)', link_url)
                    if match:
                        anime_id = match.group(1)
                        logging.debug("Anime ID: %s", anime_id)
                        ID = anime_id
                        season -= 1
                    else:
                        logging.debug("No Anime-ID found")
                        return None
                else:
                    logging.debug("No Link found in 'title'-Div")
                    return None
            else:
                logging.debug("No 'title'-Div found")
                return None
        else:
            logging.debug("Sequel (TV) not found")
            return None

    return ID

def check_episodes(ID):
    url = f"https://myanimelist.net/anime/{ID}"


    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    episodes_span = soup.find('span', class_='dark_text', string='Episodes:')

    if episodes_span and episodes_span.parent:
        episodes = episodes_span.parent.text.replace("Episodes:", "").strip()
        logging.debug("Count of the episodes %s", episodes)
        return int(episodes)
    else:
        logging.debug("The Number can not be found!")
        return None

def build_options(metadata: Dict, chapters_file: str) -> str:
    logging.debug("Building options with metadata: %s and chapters_file: %s",
                  json.dumps(metadata, indent=2), chapters_file)
    op_end, ed_start = None, None
    options = []

    for skip in metadata["results"]:
        logging.debug("Processing skip: %s", skip)
        skip_type = skip["skip_type"]
        st_time = skip["interval"]["start_time"]
        ed_time = skip["interval"]["end_time"]
        logging.debug("Skip type: %s, start time: %s, end time: %s", skip_type, st_time, ed_time)

        ch_name = None

        if skip_type == "op":
            op_end = ed_time
            ch_name = "Opening"
        elif skip_type == "ed":
            ed_start = st_time
            ch_name = "Ending"
        logging.debug("Chapter name: %s", ch_name)

        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(st_time), ftoi(ed_time), ch_name))
            logging.debug("Wrote chapter to file: %s", chapters_file)

        options.append(OPTION_FORMAT.format(skip_type, st_time, skip_type, ed_time))
        logging.debug("Options so far: %s", options)

    if op_end:
        ep_ed = ed_start if ed_start else op_end
        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(op_end), ftoi(ep_ed), "Episode"))
            logging.debug("Wrote episode chapter to file: %s", chapters_file)

    return ",".join(options)


def build_flags(ID: str, episode: int, chapters_file: str) -> str:
    logging.debug(
        "Building flags for MAL ID: %s, episode: %d, chapters_file: %s",
        ID, episode, chapters_file
    )
    aniskip_api = f"https://api.aniskip.com/v1/skip-times/{ID}/{episode}?types=op&types=ed"
    logging.debug("Fetching skip times from: %s", aniskip_api)
    response = requests.get(
        aniskip_api,
        headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
        timeout=10
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        raise_runtime_error("Failed to fetch AniSkip data.")

    metadata = response.json()
    logging.debug("AniSkip response: %s", json.dumps(metadata, indent=2))

    if not metadata.get("found"):
        logging.debug("No skip times found.")
        return ""

    with open(chapters_file, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1")
        logging.debug("Initialized chapters file: %s", chapters_file)

    options = build_options(metadata, chapters_file)
    logging.debug("Built options: %s", options)
    return f"--chapters-file={chapters_file} --script-opts={options}"


def aniskip(anime_title: str, anime_slug: str, episode: int, season: int) -> str:
    logging.debug("Running aniskip for anime_title: %s, episode: %d", anime_title, episode)
    ID = fetch_ID(anime_title, season) if not anime_title.isdigit() else anime_title
    logging.debug("Fetched MAL ID: %s", ID)
    if not ID:
        logging.debug("No MAL ID found.")
        return ""

    logging.debug("BEAAAAAAAAAAAAAAAJNNNNNNNNNNNNNNNNNNNNNNNNNSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSS %s", anime_slug)
    if check_episodes(ID) == get_season_episode_count(anime_slug, str(season)):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as chapters_file:
            logging.debug("Created temporary chapters file: %s", chapters_file.name)
            return build_flags(ID, episode, chapters_file.name)
    else:
        logging.debug("Check episode: %s", check_episodes(ID))
        logging.debug("Check get: %s",get_season_episode_count(anime_slug, str(season)))
        logging.debug("Mal ID isn't matching episode counter!")
        return ""


if __name__ == "__main__":
    #print(fetch_ID("Kaguya-sama: Love is War", 2))
    #print(aniskip("Kaguya-sama: Love is War", "kaguya-sama-love-is-war", 1, 2))
    pass
