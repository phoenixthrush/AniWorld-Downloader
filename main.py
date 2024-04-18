from argparse import ArgumentParser
from bs4 import BeautifulSoup
from hashlib import sha256
from json import loads
from os import makedirs, system, path
from re import search, findall
from urllib.parse import quote
from urllib.request import urlopen, urlretrieve
from yt_dlp import YoutubeDL
from tarfile import TarError
from tarfile import open as tarfile_open

class Options:
    def __init__(self, verbose=False, download=False, watch=True, link_only=False):
        self.verbose = verbose
        self.download = download
        self.watch = watch
        self.link_only = link_only

    @classmethod
    def from_args(cls):
        parser = ArgumentParser(description='Handle system arguments for options')
        parser.add_argument('--verbose', action='store_true', help='Enable verbose mode')
        parser.add_argument('--download', action='store_true', help='Enable download mode')
        parser.add_argument('--watch', action='store_true', help='Enable watch mode')
        parser.add_argument('--link_only', action='store_true', help='Enable link_only mode')
        
        args = parser.parse_args()
        return cls(verbose=args.verbose, download=args.download, watch=args.watch, link_only=args.link_only)


class ContentProvider:
    def __init__(self, provider, language, link):
        self.provider = provider # (VOE, Doodstream, Vidoza, Streamtape)
        self.language = language # (Deutsch, mit Untertitel Englisch, mit Untertitel Deutsch)
        self.link = f"https://aniworld.to{link}"


class Series:
    def __init__(self, episodes, series_name, filename, hls_link, video_height):
        self.episodes = episodes
        self.series = series_name
        self.filename = filename
        self.hls_link = hls_link
        self.video_height = video_height

def get_content_providers(url_with_episode):
    providers_list = []

    html_content = urlopen(url_with_episode).read().decode("utf-8")
    soup = BeautifulSoup(html_content, "html.parser")

    if 'Deine Anfrage wurde als Spam erkannt.' in soup:
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        exit()

    hostSeriesTitle = soup.find('div', class_='hostSeriesTitle')

    if hostSeriesTitle:
        series_title = hostSeriesTitle.text.strip()
    else:
        print("Could not fetch series title.")
        exit()

    language_div = soup.find('div', class_='changeLanguageBox')
    
    if language_div:
        language_tags = language_div.find_all('img')
        languages = [(tag['title'], tag['data-lang-key']) for tag in language_tags]
        
        # eng sub comes before ger sub
        if ('mit Untertitel Englisch', '2') in languages and ('mit Untertitel Deutsch', '3') in languages:
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
                series = Series(series_name=series_title, filename=None, hls_link=None, episodes=None, video_height=None)
            else:
                print("No watchEpisode link found within generateInlinePlayer div.")
                exit()

    else:
        print("Language information not found in the HTML.")
        exit()

    return providers_list, series

def get_stream_url(url, series):
    html_content = urlopen(url).read().decode("utf-8")
    if options.verbose:
        print("Stream URL Page: " + url)

    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.find("meta", {"name": "og:title", "content": True})
    if title:
        filename = title["content"]
        if options.verbose:
            print("Filename: " + filename)
    else:
        filename = None

    pattern = r"'hls': '(.*?)'"
    height_pattern = r"'video_height': (\d+),"

    match = search(pattern, html_content)
    height_match = search(height_pattern, html_content)

    if match:
        hls_link = match.group(1)
    else:
        print("HLS link not found.")
        exit()

    if height_match:
        video_height = int(height_match.group(1))
    else:
        video_height = None

    series.filename = filename
    series.hls_link = hls_link
    series.video_height = video_height

    return series

def play_hls_link(hls_link):
    try:
        if options.link_only:
            print(hls_link)
            exit()
        else:
            system("./mpv/mpv.app/Contents/MacOS/mpv " + f'"{hls_link}"' + " --quiet --really-quiet")
    except Exception as e:
        print("Could not execute mpv (mpv/mpv.app/Contents/MacOS/mpv): ", e)

def download_with_ytdlp(url, series):
    if options.link_only:
        print(url)
        exit()
    try:
        makedirs(f"Downloads/{series.series}", exist_ok = True)
    except Exception as e:
        print("Error:", e)

    try:
        yt_opts = {
            'quiet': True,
            'progress': True,
            'no_warnings': True,
            'outtmpl': f"Downloads/{series.series}/{series.filename}",
        }
        ytdlp = YoutubeDL(yt_opts)
        ytdlp.download([url])
    except Exception as e:
        print("Could not download using yt-dlp:", e)

def calculate_checksum(file_path, checksum):
    with open(file_path, "rb") as file:
        file_hash = sha256()
        while chunk := file.read(4096):
            file_hash.update(chunk)
    
    file_digest = file_hash.hexdigest()
    if file_digest != checksum:
        print("File Digest:\t\t", file_digest)
        print("Expected Digest:\t", checksum)
        print("Checksum mismatch! The downloaded file may be corrupted or tampered with.")
        exit()

    return True

def extract_tar_gz(archive_path, extract_path):
    try:
        with tarfile_open(archive_path, "r:gz") as tar:
            tar.extractall(path=extract_path)
    except TarError as e:
        print("Could not extract mpv: ", e)

def get_mpv(download = True):
    if download:
        if not path.exists("mpv/mpv.app"):
            try:
                makedirs("mpv", exist_ok = True)
                urlretrieve("https://laboratory.stolendata.net/~djinn/mpv_osx/mpv-0.37.0.tar.gz", "mpv/mpv-0.37.0.tar.gz")
            except Exception as e:
                print("Could not fetch mpv: ", e)

            # mpv-0.37.0.tar.gz - sha256:73a44595dc36b3aab6bd92e4426ede3478c5dd2d5cf8ca446b110ce520f12e47
            calculate_checksum("mpv/mpv-0.37.0.tar.gz", "73a44595dc36b3aab6bd92e4426ede3478c5dd2d5cf8ca446b110ce520f12e47")
            extract_tar_gz("mpv/mpv-0.37.0.tar.gz", "mpv/")

def search_series():
    keyword = input("Search for a series: ")
    encoded_keyword = quote(keyword)

    url = f"https://aniworld.to/ajax/seriesSearch?keyword={encoded_keyword}"
    with urlopen(url) as response:
        data = response.read()

    if "Deine Anfrage wurde als Spam erkannt." in data.decode():
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        exit()

    json_data = loads(data.decode())
    if options.verbose:
        print(f"Query JSON Data: {json_data}")

    names_with_years = [f"{entry['name']} {entry['productionYear']}" for entry in json_data]
    links = [entry['link'] for entry in json_data]

    results = []
    episode_links = []

    for name_with_year, link in zip(names_with_years, links):
        year = name_with_year[name_with_year.find("(") + 1:name_with_year.find(")")]
        name = name_with_year.split(" (")[0]
        results.append(f"{name} {year}")

    if not results:
        print("No matches found.")
        exit()

    def list_episodes(selected_link):
        series_url = f"https://aniworld.to/anime/stream/{selected_link}"
        html_content = urlopen(series_url).read().decode("utf-8")
        soup = BeautifulSoup(html_content, "html.parser")

        match = search(r'Episoden:\s*(.*)', soup.text)

        if match:
            content = match.group(1)
            last_episode = max(map(int, findall(r'\d+', content)))
        
        print(f"Available Episodes: 0-" + str(last_episode))
        return html_content

    if len(results) != 1:
        print("Available anime series:")
        for index, result in enumerate(results, 1):
            print(f"{index}. {result}")

        selection = input("Enter the number of the anime series you want to select: ")

        if selection.isdigit():
            selection = int(selection)
            if 1 <= selection <= len(results):
                selected_index = selection - 1
                selected_link = links[selected_index]
                html_content = list_episodes(selected_link)
                episodes_input = input("Enter the season and episode number(s) (e.g., S1E1 or S1E1 S1E4): ")
                if episodes_input == "":
                    episodes_input = "S1E1"
                episodes_list = episodes_input.split()
                for episode in episodes_list:
                    season_num = episode.split('S')[1].split('E')[0]
                    episode_num = episode.split('E')[1]
                    link = f"https://aniworld.to/anime/stream/{selected_link}/staffel-{season_num}/episode-{episode_num}"
                    if options.verbose:
                        print(link)
                    episode_links.append(link)
            else:
                print(f"Invalid selection. Please enter a number between 1 and {len(results)}.")
        else:
            print("Invalid input. Please enter a number.")
    else:
        selected_link = links[0]
        html_content = list_episodes(selected_link)
        episodes_input = input("Enter the season and episode number(s) (e.g., S1E1 or S1E1 S1E4): ")
        if episodes_input == "":
            episodes_input = "S1E1"
        episodes_list = episodes_input.split()
        for episode in episodes_list:
            season_num = episode.split('S')[1].split('E')[0]
            episode_num = episode.split('E')[1]
            link = f"https://aniworld.to/anime/stream/{selected_link}/staffel-{season_num}/episode-{episode_num}"
            episode_links.append(link)

        return episode_links, html_content
        

def select_language(languages):
    print("Available Languages:")
    for idx, language in enumerate(languages, 1):
        print(f"{idx}. {language}")

    language_selection = input("Enter the number of the language you want to select: ")

    if language_selection.isdigit():
        language_selection = int(language_selection)
        if 1 <= language_selection <= len(languages):
            selected_language = languages[language_selection - 1]
            if options.verbose:
                print(f"You've selected: {selected_language}")
            return selected_language
        else:
            print(f"Invalid selection. Please enter a number between 1 and {len(languages)}.")
            return select_language(languages)
    else:
        print("Invalid input. Please enter a number.")
        return select_language(languages)

if __name__ == "__main__":
    options = Options.from_args()

    try:
        episode_links, html_content = search_series()
        url_with_episode = episode_links[0] # debug

        providers, series = get_content_providers(url_with_episode)

        """ # all links
        for provider in providers:
            print("Provider:", provider.provider)
            print("Language:", provider.language)
            print("Link:", provider.link)
            print()
        """

        available_languages = [provider.language for provider in providers if provider.provider == "VOE"]
        selected_language = select_language(available_languages)

        for provider in providers:
            if provider.provider == "VOE" and provider.language == selected_language:
                series = get_stream_url(provider.link, series)
                if not options.watch and not options.download:
                    options.download = True
                if options.watch and not options.download:
                    get_mpv()
                    play_hls_link(series.hls_link)
                elif options.download and not options.watch:
                    download_with_ytdlp(series.hls_link, series)

    except KeyboardInterrupt:
        print()
        print("KeyboardInterrupt received.")