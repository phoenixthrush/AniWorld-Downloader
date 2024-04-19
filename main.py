"""
AniWorld Downloader is a command-line tool designed to download content from aniworld.to.
It offers various features, including fetching single episodes, downloading entire seasons,
organizing downloads into structured directories, and supporting multiple operating systems.
"""

from argparse import ArgumentParser
from hashlib import sha256
from json import loads
from os import makedirs, system, path
from platform import system as platform
from re import search, findall, match
from sys import exit as shutdown
from tarfile import TarError, open as tarfile_open
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen, urlretrieve

from bs4 import BeautifulSoup
from py7zr import SevenZipFile
from yt_dlp import YoutubeDL, DownloadError


class Options:  # pylint: disable=too-few-public-methods, too-many-arguments
    """
    Handles system arguments for options.
    """
    def __init__(self, link=None, verbose=False, download=False, watch=True, link_only=False):
        self.link = link
        self.verbose = verbose
        self.download = download
        self.watch = watch
        self.link_only = link_only

    @classmethod
    def from_args(cls):
        """
        Creates an Options object based on command-line arguments.

        Parses command-line arguments to determine the options specified by the user
        and initializes an Options object accordingly.

        Returns:
            Options: An Options object representing the specified command-line options.
        """
        parser = ArgumentParser(description='Handle system arguments for options')
        parser.add_argument('--link', help='Aniworld.to link')
        parser.add_argument('--verbose', action='store_true', help='Enable verbose mode')
        parser.add_argument('--download', action='store_true', help='Enable download mode')
        parser.add_argument('--watch', action='store_true', help='Enable watch mode')
        parser.add_argument('--link_only', action='store_true', help='Enable link_only mode')

        args = parser.parse_args()

        if args.link:
            aniworld_pattern = r'https?://aniworld\.to/anime/stream/[^/]+/staffel-\d+/episode-\d+'
            if not match(aniworld_pattern, args.link):
                print("The provided link does not match the aniworld.to episode link pattern.")
                args.link = None

        return cls(
            link=args.link,
            verbose=args.verbose,
            download=args.download,
            watch=args.watch,
            link_only=args.link_only
        )


class ContentProvider:  # pylint: disable=too-few-public-methods
    """
    Represents a content provider for streaming anime episodes.

    This class encapsulates information about a content provider, including its name,
    language, and link.

    Attributes:
        provider (str): The name of the content provider (e.g., VOE, Doodstream).
        language (str): The language of the content (e.g., Deutsch, mit Untertitel Englisch).
        link (str): The URL link to the content provider.
    """
    def __init__(self, provider, language, link):
        self.provider = provider
        self.language = language
        self.link = f"https://aniworld.to{link}"


class Series:  # pylint: disable=too-few-public-methods, too-many-arguments
    """
    Represents a series of anime episodes.

    This class stores information about a series, including its name, episodes,
    filename, HLS link, and video height.
    """
    def __init__(self, episodes, series_name, filename, hls_link, episode_title):
        self.episodes = episodes
        self.series = series_name
        self.filename = filename
        self.hls_link = hls_link
        self.episode_title = episode_title


def get_content_providers(url_with_episode):  # pylint: disable=too-many-locals # :D
    """
    Fetches content providers for a given URL with episodes.

    Args:
        url_with_episode (str): The URL containing the episode.

    Returns:
        tuple: A tuple containing a list of ContentProvider objects and a Series object.
    """
    providers_list = []

    with urlopen(url_with_episode) as response:
        html_content_inner = response.read().decode("utf-8")

    soup = BeautifulSoup(html_content_inner, "html.parser")

    if 'Deine Anfrage wurde als Spam erkannt.' in soup:
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        shutdown()

    host_series_title = soup.find('div', class_='hostSeriesTitle')
    series_title = host_series_title.text.strip() if host_series_title else None

    language_div = soup.find('div', class_='changeLanguageBox')

    if language_div:
        language_tags = language_div.find_all('img')
        languages = [(tag['title'], tag['data-lang-key']) for tag in language_tags]

        # eng sub comes before ger sub
        if ('mit Untertitel Englisch', '2') in languages and \
           ('mit Untertitel Deutsch', '3') in languages:
            index_2 = languages.index(('mit Untertitel Englisch', '2'))
            index_3 = languages.index(('mit Untertitel Deutsch', '3'))
            languages[index_3], languages[index_2] = languages[index_2], languages[index_3]

        inline_player_divs = soup.find_all('div', class_='generateInlinePlayer')

        for idx, div in enumerate(inline_player_divs):

            a_tag = div.find('a', class_='watchEpisode')
            if a_tag:

                redirect_link = a_tag.get('href')
                hoster = a_tag.find('h4').text

                language = languages[idx % len(languages)][0]

                provider = ContentProvider(provider=hoster, language=language, link=redirect_link)
                providers_list.append(provider)
                series = Series(
                    series_name=series_title,
                    filename=None,
                    hls_link=None,
                    episodes=None,
                    episode_title=soup.find("span", class_="episodeGermanTitle").text
                )
            else:
                print("No watchEpisode link found within generateInlinePlayer div.")
                shutdown()
    else:
        print("Language information not found in the HTML.")
        shutdown()

    return providers_list, series


def get_stream_url(url, series):
    """
    Retrieves the HLS stream URL and related information from the provided URL.

    Args:
        url (str): The URL of the page containing the HLS stream information.
        series (Series): An instance of the Series class representing the anime series.

    Returns:
        Series: An updated instance of the Series class with the HLS stream URL
        and related information.
    """
    with urlopen(url) as response:
        html_content_inner = response.read().decode("utf-8")
    if options.verbose:
        print("Stream URL Page: " + url)

    soup = BeautifulSoup(html_content_inner, "html.parser")
    title = soup.find("meta", {"name": "og:title", "content": True})
    if title:
        filename = title["content"]
        if options.verbose:
            print("Filename: " + filename)
    else:
        filename = None

    pattern = r"'hls': '(.*?)'"
    match_hls = search(pattern, html_content_inner)

    if match_hls:
        hls_link = match_hls.group(1)
    else:
        print("HLS link not found.")
        shutdown()

    series.filename = filename
    series.hls_link = hls_link

    return series


def play_hls_link(hls_link):
    """
    Plays the HLS link using the MPV media player.

    Args:
        hls_link (str): The HLS link to play.

    Returns:
        None
    """
    mpv_title = (
        f"{updated_series.series} - "
        f"{updated_series.episode_title}"
    )

    if options.link_only:
        print(hls_link)
        shutdown()
    else:
        os = platform()
        if os == "Linux":
            system(
                f"mpv \"{hls_link}\" "
                f"--quiet --really-quiet --title=\"{mpv_title}\""
            )
        elif os == "Darwin":
            system(
                f"./mpv/mpv.app/Contents/MacOS/mpv \"{hls_link}\" "
                f"--quiet --really-quiet --title=\"{mpv_title}\""
            )
        elif os == "Windows":
            system(
                f".\\mpv\\mpv.exe \"{hls_link}\" "
                f"--quiet --really-quiet --title=\"{mpv_title}\""
            )
        else:
            print("Could not determine OS.")
            shutdown()


def download_with_ytdlp(url, series):
    """
    Downloads the video using youtube-dl.

    Args:
        url (str): The URL of the video to download.
        series (Series): An instance of the Series class representing the anime series.

    Returns:
        None
    """
    if options.link_only:
        print(url)
        shutdown()
    try:
        makedirs(f"Downloads/{series.series}", exist_ok=True)
    except FileExistsError as e:
        print("Error creating directory:", e)

    try:
        yt_opts = {
            'quiet': True,
            'progress': True,
            'no_warnings': True,
            'outtmpl': f"Downloads/{series.series}/{series.filename}",
        }
        ytdlp = YoutubeDL(yt_opts)
        ytdlp.download([url])
    except DownloadError as e:
        print("Could not download using yt-dlp:", e)


def calculate_checksum(file_path, checksum):
    """
    Calculates the checksum of a file and compares it with the provided checksum.

    Args:
        file_path (str): The path to the file.
        checksum (str): The expected checksum value.

    Returns:
        bool: True if the calculated checksum matches the expected checksum, False otherwise.
    """
    with open(file_path, "rb") as file:
        file_hash = sha256()
        while chunk := file.read(4096):
            file_hash.update(chunk)

    file_digest = file_hash.hexdigest()
    if file_digest != checksum:
        print("File Digest:\t\t", file_digest)
        print("Expected Digest:\t", checksum)
        print("Checksum mismatch! The downloaded file may be corrupted or tampered with.")
        return False

    return True


def extract_zip(archive_path, extract_path):
    """
    Extracts a gzip-compressed tar archive or a 7z archive to a specified directory.

    Args:
        archive_path (str): The path to the archive.
        extract_path (str): The directory where the contents of the archive will be extracted.

    Raises:
        TarError: If an error occurs during the extraction process for tar archives.
        Exception: If an error occurs during the extraction process for 7z archives.
    """
    file_extension = archive_path.split('.')
    if file_extension[-1] == "gz":
        try:
            with tarfile_open(archive_path, "r:gz") as tar:
                tar.extractall(path=extract_path)
        except TarError as e:
            print("Could not extract mpv:", e)
            shutdown()
    elif file_extension[-1] == "7z":
        with SevenZipFile(archive_path, mode='r') as z:
            z.extractall(path=extract_path)


def get_mpv(download=True):
    """
    Downloads and extracts the MPV media player if it's not already downloaded.

    Args:
        download (bool, optional): Flag indicating whether to download MPV
                                   if not already downloaded.
                                   Defaults to True.

    Returns:
        None

    Notice:
        Windows:
            Difference between x86_64 and x86_64-v3:
            x86_64-v3 build have these instructions enabled by default:
            avx avx2 bmi bmi2 fma lzcnt movbe sse3 sse4 sse4.1
            sse4.2 ssse3 xsave sahf mwait crc32 cx16 popcnt f16c
            CPU which don't have these features will fail to launch the x86_64-v3 build

            To download the latest file, open the following link in your browser:
            https://sourceforge.net/projects/mpv-player-windows/files/64bit/

            Then update the URL retrieval to the desired link.
            The downloaded mpv build for Windows does not currently have a checksum.
    """
    if download:
        os = platform()
        if os == "Darwin":
            if not path.exists("mpv/mpv.app"):
                try:
                    makedirs("mpv", exist_ok=True)
                    urlretrieve("https://laboratory.stolendata.net/~djinn/"
                                "mpv_osx/mpv-0.37.0.tar.gz",
                                "mpv/mpv-0.37.0.tar.gz")
                except FileNotFoundError as e:
                    print("Could not find the directory: ", e)
                except URLError as e:
                    print("URL retrieval error: ", e)

                # mpv-0.37.0.tar.gz
                # sha256:73a44595dc36b3aab6bd92e4426ede3478c5dd2d5cf8ca446b110ce520f12e47
                if not calculate_checksum("mpv/mpv-0.37.0.tar.gz",
                                          "73a44595dc36b3aab6bd92e4426ede3478c5dd2d5cf8ca"
                                          "446b110ce520f12e47"):
                    shutdown()
                extract_zip("mpv/mpv-0.37.0.tar.gz", "mpv/")
        elif os == "Windows":
            if not path.exists("mpv/"):
                try:
                    makedirs("mpv", exist_ok=True)
                    urlretrieve("https://sourceforge.net/projects/mpv-player-windows/"
                                "files/latest/download",
                                "mpv/mpv-x86_64-v3-latest-git.7z")
                except FileNotFoundError as e:
                    print("Could not find the directory: ", e)
                except URLError as e:
                    print("URL retrieval error: ", e)
                extract_zip("mpv/mpv-x86_64-v3-latest-git.7z", "mpv/")
        else:
            print("Could not determine OS.")
            shutdown()


def search_series():
    """
    Searches for a series based on user input, selects a series from the results,
    and lists available episodes.

    Returns:
        tuple: A tuple containing a list of episode links
               and the HTML content of the series page.
    """
    keyword = input("Search for a series: ")
    encoded_keyword = quote(keyword)
    url = f"https://aniworld.to/ajax/seriesSearch?keyword={encoded_keyword}"

    with urlopen(url) as response:
        data = response.read()

    if "Deine Anfrage wurde als Spam erkannt." in data.decode():
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        shutdown()

    json_data = loads(data.decode())
    if options.verbose:
        print(f"Query JSON Data: {json_data}")

    results = parse_results(json_data)
    if not results:
        print("No matches found.")
        shutdown()

    selected_link = select_series(results)
    inner_episode_links, inner_html_content = list_episodes(selected_link)
    return inner_episode_links, inner_html_content


def parse_results(json_data):
    """
    Parses the JSON data to extract series names and links.

    Args:
        json_data (list): List of JSON data representing series.

    Returns:
        list: A list of tuples containing series names and links.
    """
    names_with_years = [f"{entry['name']} {entry['productionYear']}" for entry in json_data]
    links = [entry['link'] for entry in json_data]
    return list(zip(names_with_years, links))


def select_series(results):
    """
    Selects a series from the search results.

    Args:
        results (list): List of tuples containing series names and links.

    Returns:
        str: The selected series link.
    """
    if len(results) != 1:
        print("Available anime series:")
        for index, (name, _) in enumerate(results, 1):
            print(f"{index}. {name}")

        selection = input("Enter the number of the anime series you want to select: ")
        return select_series_from_input(selection, results)
    return results[0][1]


def select_series_from_input(selection, results):
    """
    Handles user input to select a series.

    Args:
        selection (str): The user's selection.
        results (list): List of tuples containing series names and links.

    Returns:
        str: The selected series link.
    """
    if selection.isdigit():
        selection = int(selection)
        if 1 <= selection <= len(results):
            return results[selection - 1][1]
        print(f"Invalid selection. Please enter a number between 1 and {len(results)}.")
    else:
        print("Invalid input. Please enter a number.")
    return select_series(results)


def list_episodes(selected_link):
    """
    Lists available episodes for the selected series.

    Args:
        selected_link (str): The link of the selected series.

    Returns:
        tuple: A tuple containing a list of episode links and the HTML content of the series page.
    """
    series_url = f"https://aniworld.to/anime/stream/{selected_link}"

    with urlopen(series_url) as response:
        inner_html_content = response.read().decode("utf-8")

    soup = BeautifulSoup(inner_html_content, "html.parser")
    last_episode = get_last_episode(soup)

    print("Available Episodes: 0-" + str(last_episode))

    return get_episode_links(selected_link), inner_html_content


def get_last_episode(soup):
    """
    Extracts the last episode number from the HTML content.

    Args:
        soup: BeautifulSoup object representing the HTML content of the series page.

    Returns:
        int: The last episode number.
    """
    match_last_ep = search(r'Episoden:\s*(.*)', soup.text)
    if match_last_ep:
        content = match_last_ep.group(1)
        return max(map(int, findall(r'\d+', content)))
    return 0


def get_episode_links(selected_link):
    """
    Constructs episode links based on user input.

    Args:
        soup: BeautifulSoup object representing the HTML content of the series page.
        selected_link (str): The link of the selected series.

    Returns:
        list: A list of episode links.
    """
    episodes_input = input("Enter the season and episode number(s) (e.g., S1E1 or S1E1 S1E2): ")
    if episodes_input == "":
        episodes_input = "S1E1"
    episodes_list = episodes_input.split()
    episode_links = []
    for episode in episodes_list:
        try:
            season_num = episode.split('S')[1].split('E')[0]
            episode_num = episode.split('E')[1]
            link = (
                f"https://aniworld.to/anime/stream/{selected_link}/"
                f"staffel-{season_num}/episode-{episode_num}"
            )
        except IndexError:
            print("Invalid Input.")
            shutdown()
        if options.verbose:
            print(link)
        episode_links.append(link)

    return episode_links


def select_language(languages):
    """
    Allows the user to select a language from a list of available languages.

    Args:
        languages (list): A list of available languages.

    Returns:
        str: The selected language.
    """
    print("Available Languages:")
    for idx, language in enumerate(languages, 1):
        print(f"{idx}. {language}")

    while True:
        language_selection = input("Enter the number of the language you want to select: ")

        if language_selection.isdigit():
            language_index = int(language_selection) - 1
            if 0 <= language_index < len(languages):
                inner_selected_language = languages[language_index]
                if options.verbose:
                    print(f"You've selected: {inner_selected_language}")
                return inner_selected_language
            print(f"Invalid selection. Please enter a number between 1 and {len(languages)}.")
        else:
            print("Invalid input. Please enter a number.")


if __name__ == "__main__":
    options = Options.from_args()

    try:
        if options.link:
            url_with_episode_debug = options.link
        else:
            episode_links_outer, html_content = search_series()
            url_with_episode_debug = episode_links_outer[0]  # Debug: always first entered episode

        providers, initial_series = get_content_providers(url_with_episode_debug)

        provider_languages = [
            provider.language for provider in providers if provider.provider == "VOE"
        ]
        selected_language = select_language(provider_languages)

        updated_series = initial_series

        for provider_outer in providers:
            if provider_outer.provider == "VOE" and provider_outer.language == selected_language:
                updated_series = get_stream_url(provider_outer.link, updated_series)
                if not options.watch and not options.download:
                    options.download = True
                if options.watch and not options.download:
                    get_mpv()
                    play_hls_link(updated_series.hls_link)
                elif options.download and not options.watch:
                    download_with_ytdlp(updated_series.hls_link, updated_series)

    except KeyboardInterrupt:
        print()
        print("KeyboardInterrupt received.")
