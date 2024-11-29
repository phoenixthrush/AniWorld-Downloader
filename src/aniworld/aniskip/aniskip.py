import re
import logging

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 15


def get_mal_id_from_title(title: str, season: int) -> int:
    logging.debug("Fetching MAL ID for: %s", title)

    name = re.sub(r' \(\d+ episodes\)', '', title)
    logging.debug("Processed name: %s", name)

    keyword = re.sub(r'\s+', '%20', name)
    logging.debug("Keyword for search: %s", keyword)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        timeout=REQUEST_TIMEOUT
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        logging.error("Failed to fetch MyAnimeList data. HTTP Status: %d", response.status_code)
        raise ValueError("Error fetching data from MyAnimeList.")

    mal_metadata = response.json()
    results = [
        entry for entry in mal_metadata['categories'][0]['items']
        if 'OVA' not in entry['name']
    ]
    logging.debug("Search results: %s", results)

    if not results:
        logging.error("No match found!")
        raise ValueError("No match found!")

    best_match = results[0]
    logging.debug("Best match: %s", best_match)

    for entry in mal_metadata['categories'][0]['items']:
        if entry['name'] == best_match['name']:
            anime_id = entry['id']
            logging.debug("Found MAL ID: %s for %s", anime_id, best_match)

            while season > 1:
                url = f"https://myanimelist.net/anime/{anime_id}"
                logging.debug("Fetching URL: %s", url)

                response = requests.get(url, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                sequel_div = soup.find("div", string=lambda text: text and "Sequel" in text and "(TV)" in text)

                if not sequel_div:
                    error_msg = "Sequel (TV) not found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                title_div = sequel_div.find_next("div", class_="title")
                if not title_div:
                    error_msg = "No 'title'-Div found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_element = title_div.find("a")
                if not link_element:
                    error_msg = "No Link found in 'title'-Div"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_url = link_element.get("href")
                logging.debug("Found Link: %s", link_url)
                match = re.search(r'/anime/(\d+)', link_url)

                if not match:
                    error_msg = "No Anime-ID found in the link URL"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                anime_id = match.group(1)
                logging.debug("Anime ID: %s", anime_id)
                season -= 1

            return anime_id

    error_msg = "No match found!"
    logging.error(error_msg)
    raise ValueError(error_msg)
