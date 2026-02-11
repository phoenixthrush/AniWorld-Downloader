import importlib
import json
import logging
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Any

import requests
import requests.models
from bs4 import BeautifulSoup

from .aniskip import get_mal_id_from_title
from .config import (
    DEFAULT_REQUEST_TIMEOUT,
    RANDOM_USER_AGENT,
    SUPPORTED_SITES,
    SITE_LANGUAGE_CODES,
    SITE_LANGUAGE_NAMES,
    SUPPORTED_PROVIDERS,
    S_TO,
)
from .parser import arguments
from .common import get_season_episode_count, get_movie_episode_count


class Anime:
    """
    Represents an anime series with comprehensive data management and validation.

    This class provides a complete interface for anime data including metadata,
    episode management, and provider/language configuration with lazy loading
    and caching for optimal performance.

    Supports multiple streaming sites:
    - ANIWORLD_TO (default)
    - S_TO

    Example:
        anime = Anime(
            episode_list=[
                Episode(
                    slug="loner-life-in-another-world",
                    season=1,
                    episode=1,
                    site="aniworld.to"  # Optional, defaults to aniworld.to
                )
            ]
        )

    Required Attributes:
        episode_list (List[Episode]): A list of Episode objects for the anime.

    Attributes:
        title (str): The title of the anime.
        slug (str): A URL-friendly version of the title used for web requests.
        site (str): The streaming site to use (ANIWORLD_TO or S_TO).
        action (str): The default action to be performed ("Download", "Watch", "Syncplay").
        provider (str): The provider of the anime content.
        language (str): The language code for the anime.
        aniskip (bool): Whether to skip certain actions (default is False).
        output_directory (str): The directory where downloads are saved.
        episode_list (List[Episode]): A list of Episode objects for the anime.
        description_german (str): The German description of the anime.
        description_english (str): The English description of the anime.
        html (requests.models.Response): The HTML response object for the anime's webpage.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        slug: Optional[str] = None,
        site: str = "aniworld.to",
        action: Optional[str] = None,
        provider: Optional[str] = None,
        language: Optional[str] = None,
        aniskip: bool = False,
        output_directory: Optional[str] = None,
        episode_list: Optional[List["Episode"]] = None,
        description_german: Optional[str] = None,
        description_english: Optional[str] = None,
        html: Optional[requests.models.Response] = None,
    ) -> None:
        """
        Initialize an Anime instance with comprehensive validation.

        Args:
            title: The anime title
            slug: URL-friendly anime identifier
            site: Streaming site to use (ANIWORLD_TO or S_TO)
            action: Action to perform (Watch/Download/Syncplay)
            provider: Streaming provider
            language: Language preference
            aniskip: Whether to skip intro/outro
            output_directory: Download directory
            episode_list: List of Episode objects
            description_german: German description
            description_english: English description
            html: Pre-fetched HTML response

        Raises:
            ValueError: If episode_list is empty or slug cannot be determined
            requests.RequestException: If fetching anime data fails
        """
        # Validate required parameters
        if not episode_list:
            raise ValueError("Provide 'episode_list' with at least one episode.")

        # Validate site
        if site not in SUPPORTED_SITES:
            raise ValueError(
                f"Unsupported site: {site}. Supported sites: {list(SUPPORTED_SITES.keys())}"
            )

        self.site = site
        self.site_config = SUPPORTED_SITES[site]
        self.base_url = self.site_config["base_url"]
        self.stream_path = self.site_config["stream_path"]

        # Extract slug from episode list if not provided
        self.slug = slug or self._extract_slug_from_episodes(episode_list)
        if not self.slug:
            raise ValueError(
                "Slug of Anime is None and cannot be determined from episodes."
            )

        # Initialize attributes with fallbacks to parser arguments
        self.action = action or getattr(arguments, "action", "Watch")
        self.provider = provider or getattr(arguments, "provider", None)
        self.language = language or getattr(arguments, "language", "German Sub")
        self.aniskip = aniskip or getattr(arguments, "aniskip", False)
        self.output_directory = output_directory or getattr(arguments, "output_dir", "")
        self.episode_list = episode_list

        # Initialize HTML and title
        self._html_cache = html
        self._title_cache = title
        self._description_german_cache = description_german
        self._description_english_cache = description_english

        # Shared anime-level data cache for episodes
        self._shared_season_episode_count = None
        self._shared_movie_episode_count = None

        # Populate shared data for episodes to avoid duplicate requests
        self._populate_shared_episode_data()

    def _extract_slug_from_episodes(
        self, episode_list: List["Episode"]
    ) -> Optional[str]:
        """
        Extract slug from the first episode in the list.

        Args:
            episode_list: List of Episode objects

        Returns:
            Slug string or None if not found
        """
        try:
            return episode_list[0].slug if episode_list else None
        except (IndexError, AttributeError):
            return None

    @property
    def html(self) -> requests.models.Response:
        """
        Lazy-loaded HTML response for the anime page.

        Returns:
            HTML response object

        Raises:
            requests.RequestException: If HTTP request fails
        """
        if self._html_cache is None:
            try:
                self._html_cache = requests.get(
                    f"{self.base_url}/{self.stream_path}/{self.slug}",
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                    headers={"User-Agent": RANDOM_USER_AGENT},
                )
                self._html_cache.raise_for_status()
            except requests.RequestException as err:
                logging.error(
                    "Failed to fetch anime HTML for slug '%s' on site '%s': %s",
                    self.slug,
                    self.site,
                    err,
                )
                raise

        return self._html_cache

    @property
    def title(self) -> str:
        """
        Lazy-loaded anime title.

        Returns:
            Anime title string
        """
        if self._title_cache is None:
            try:
                self._title_cache = get_anime_title_from_html(self.html, self.site)
                if not self._title_cache:
                    self._title_cache = f"Unknown Anime ({self.slug})"
                    logging.warning(
                        "Could not extract title for anime slug: %s", self.slug
                    )
            except Exception as err:
                logging.error("Error extracting anime title: %s", err)
                self._title_cache = f"Unknown Anime ({self.slug})"

        return self._title_cache

    @property
    def description_german(self) -> str:
        """
        Lazy-loaded German description.

        Returns:
            German description string
        """
        if self._description_german_cache is None:
            self._description_german_cache = self._fetch_description_german()

        return self._description_german_cache

    @property
    def description_english(self) -> str:
        """
        Lazy-loaded English description.

        Returns:
            English description string
        """
        if self._description_english_cache is None:
            self._description_english_cache = self._fetch_description_english()

        return self._description_english_cache

    def _fetch_description_german(self) -> str:
        """
        Fetch German description from anime HTML.

        Returns:
            German description or fallback message
        """
        try:
            soup = BeautifulSoup(self.html.content, "html.parser")
            desc_div = soup.find("p", class_="seri_des")

            if desc_div:
                description = desc_div.get("data-full-description", "")
                if description:
                    return description

                # Fallback to div text content
                return desc_div.get_text(strip=True)

            return "Could not fetch German description."

        except Exception as err:
            logging.error("Error fetching German description: %s", err)
            return "Error fetching German description."

    def _fetch_description_english(self) -> str:
        """
        Fetch English description from MyAnimeList.

        Returns:
            English description or fallback message
        """
        try:
            anime_id = get_mal_id_from_title(self.title, 1)
            if not anime_id:
                return "Could not find MyAnimeList ID for English description."

            response = requests.get(
                f"https://myanimelist.net/anime/{anime_id}",
                timeout=DEFAULT_REQUEST_TIMEOUT,
                headers={"User-Agent": RANDOM_USER_AGENT},
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            desc_meta = soup.find("meta", property="og:description")

            if desc_meta and desc_meta.get("content"):
                return desc_meta["content"]

            return "Could not fetch English description."

        except Exception as err:
            logging.error("Error fetching English description: %s", err)
            return "Error fetching English description."

    def validate_configuration(self) -> List[str]:
        """
        Validate anime configuration and return any issues.

        Returns:
            List of validation error messages
        """
        issues = []

        if not self.episode_list:
            issues.append("No episodes provided")

        if not self.slug:
            issues.append("No slug provided")

        if self.site not in SUPPORTED_SITES:
            issues.append(f"Unsupported site: {self.site}")

        if self.action not in ["Watch", "Download", "Syncplay"]:
            issues.append(f"Invalid action: {self.action}")

        # Use site-specific language codes for validation
        site_language_codes = SITE_LANGUAGE_CODES.get(self.site)
        if not site_language_codes or self.language not in site_language_codes:
            valid_languages = (
                list(site_language_codes.keys()) if site_language_codes else []
            )
            issues.append(
                f"Invalid language: {self.language}. Valid options for {self.site}: {valid_languages}"
            )

        return issues

    def __iter__(self) -> iter:
        """Iterate over episode list."""
        return iter(self.episode_list)

    def __getitem__(self, index: int) -> "Episode":
        """Get episode by index."""
        return self.episode_list[index]

    def __len__(self) -> int:
        """Get number of episodes."""
        return len(self.episode_list)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert anime to dictionary representation.

        Returns:
            Dictionary with anime data
        """
        return {
            "title": self.title,
            "slug": self.slug,
            "site": self.site,
            "action": self.action,
            "provider": self.provider,
            "language": self.language,
            "aniskip": self.aniskip,
            "output_directory": str(self.output_directory),
            "episode_count": len(self.episode_list),
            "description_german": self._truncate_description(self.description_german),
            "description_english": self._truncate_description(self.description_english),
        }

    def _truncate_description(self, description: str, max_words: int = 10) -> str:
        """
        Truncate description to specified word count.

        Args:
            description: Description text
            max_words: Maximum number of words

        Returns:
            Truncated description with ellipsis if needed
        """
        if not description:
            return ""

        words = description.split()
        if len(words) <= max_words:
            return description

        return " ".join(words[:max_words]) + " [...]"

    def _populate_shared_episode_data(self) -> None:
        """
        Populate shared anime-level data once to be used by all episodes.
        This prevents each episode from making duplicate HTTP requests.
        """
        try:
            if self.slug and not self._shared_season_episode_count:
                # Get the first episode link for reference
                first_episode_link = None
                if self.episode_list:
                    first_episode_link = getattr(self.episode_list[0], "link", None)

                if not first_episode_link and self.episode_list:
                    # Try to construct a link from first episode data
                    first_ep = self.episode_list[0]
                    if (
                        first_ep.slug
                        and first_ep.season is not None
                        and first_ep.episode is not None
                    ):
                        if first_ep.season == 0:
                            first_episode_link = f"{self.base_url}/{self.stream_path}/{first_ep.slug}/filme/film-{first_ep.episode}"
                        else:
                            first_episode_link = f"{self.base_url}/{self.stream_path}/{first_ep.slug}/staffel-{first_ep.season}/episode-{first_ep.episode}"

                # Fetch shared data
                self._shared_season_episode_count = get_season_episode_count(
                    self.slug,
                    first_episode_link
                    or f"{self.base_url}/{self.stream_path}/{self.slug}",
                )
                self._shared_movie_episode_count = get_movie_episode_count(self.slug)

                # Share this data with all episodes
                for episode in self.episode_list:
                    if not episode.season_episode_count:
                        episode.season_episode_count = self._shared_season_episode_count
                    if (
                        episode.movie_episode_count is None
                        or episode.movie_episode_count == 0
                    ):
                        episode.movie_episode_count = self._shared_movie_episode_count

        except Exception as err:
            logging.error("Error populating shared episode data: %s", err)

    def to_json(self) -> str:
        """
        Convert anime to JSON string representation.

        Returns:
            JSON string with anime data
        """
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def __str__(self) -> str:
        """String representation of anime."""
        return (
            f"Anime(title='{self.title}', "
            f"episodes={len(self.episode_list)}, "
            f"action='{self.action}')"
        )

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"Anime(title='{self.title}', slug='{self.slug}', "
            f"episodes={len(self.episode_list)}, action='{self.action}', "
            f"provider='{self.provider}', language='{self.language}')"
        )


class Episode:
    """
    Represents an episode of an anime series with comprehensive data management.

    This class provides a complete interface for episode data including metadata,
    provider/language management, and streaming link generation with lazy loading
    and caching for optimal performance.

    Supports multiple streaming sites:
    - ANIWORLD_TO (default)
    - S_TO

    Example:
        Episode(
            slug="loner-life-in-another-world",
            season=1,
            episode=1,
            site="aniworld.to"  # Optional, defaults to aniworld.to
        )

    Required Attributes:
        link (str) OR (slug (str) + season (int) + episode (int)):
        Either a direct link to the episode or components to construct it.

    Attributes:
        anime_title (str): The title of the anime the episode belongs to.
        title_german (str): The German title of the episode.
        title_english (str): The English title of the episode.
        season (int): The season number (0 for movies).
        episode (int): The episode number within the season.
        slug (str): URL-friendly anime identifier.
        site (str): The streaming site (ANIWORLD_TO or S_TO).
        link (str): The direct link to the episode page.
        mal_id (int): The MyAnimeList ID for the episode.
        redirect_link (str): The redirect link for streaming.
        embeded_link (str): The embedded streaming link.
        direct_link (str): The direct streaming link.
        provider (Dict[str, Dict[int, str]]): Available providers and their links.
        provider_name (List[str]): List of provider names.
        language (List[int]): List of available language codes.
        language_name (List[str]): List of available language names.
        season_episode_count (Dict[int, int]): Season to episode count mapping.
        movie_episode_count (int): Number of movie episodes.
        html (requests.models.Response): HTML response object.
        _selected_provider (str): Currently selected provider.
        _selected_language (str): Currently selected language.
    """

    def __init__(
        self,
        anime_title: Optional[str] = None,
        title_german: Optional[str] = None,
        title_english: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        slug: Optional[str] = None,
        site: str = "aniworld.to",
        link: Optional[str] = None,
        mal_id: Optional[int] = None,
        redirect_link: Optional[str] = None,
        embeded_link: Optional[str] = None,
        direct_link: Optional[str] = None,
        provider: Optional[Dict[str, Dict[int, str]]] = None,
        provider_name: Optional[List[str]] = None,
        language: Optional[List[int]] = None,
        language_name: Optional[List[str]] = None,
        season_episode_count: Optional[Dict[int, int]] = None,
        has_movies: bool = False,
        movie_episode_count: Optional[int] = None,
        html: Optional[requests.models.Response] = None,
        _selected_provider: Optional[str] = None,
        _selected_language: Optional[str] = None,
    ) -> None:
        """
        Initialize an Episode instance with comprehensive validation.

        Args:
            anime_title: Anime title
            title_german: German episode title
            title_english: English episode title
            season: Season number (0 for movies)
            episode: Episode number
            slug: Anime slug identifier
            site: Streaming site to use (ANIWORLD_TO or S_TO)
            link: Direct episode link
            mal_id: MyAnimeList ID
            redirect_link: Redirect streaming link
            embeded_link: Embedded streaming link
            direct_link: Direct streaming link
            provider: Available providers dictionary
            provider_name: List of provider names
            language: Available language codes
            language_name: Available language names
            season_episode_count: Season episode counts
            has_movies: Whether anime has movies
            movie_episode_count: Number of movies
            html: Pre-fetched HTML response
            _selected_provider: Selected provider
            _selected_language: Selected language

        Raises:
            ValueError: If neither link nor (slug + season + episode) provided
        """
        # Validate required parameters
        if not link and (not slug or season is None or episode is None):
            raise ValueError(
                "Provide either 'link' or 'slug' with 'season' and 'episode'."
            )

        # Validate site
        if site not in SUPPORTED_SITES:
            raise ValueError(
                f"Unsupported site: {site}. Supported sites: {list(SUPPORTED_SITES.keys())}"
            )

        self.site = site
        self.site_config = SUPPORTED_SITES[site]
        self.base_url = self.site_config["base_url"]
        self.stream_path = self.site_config["stream_path"]

        # Initialize core attributes
        self.anime_title = anime_title
        self.title_german = title_german
        self.title_english = title_english
        self.season = season
        self.episode = episode
        self.slug = slug
        self.link = link
        self.mal_id = mal_id

        # Initialize streaming attributes
        self.redirect_link = redirect_link
        self.embeded_link = embeded_link
        self.direct_link = direct_link

        # Initialize provider and language data
        self.provider = provider or {}
        self.provider_name = provider_name or []
        self.language = language or []
        self.language_name = language_name or []

        # Initialize metadata
        self.season_episode_count = season_episode_count or {}
        self.has_movies = has_movies
        self.movie_episode_count = movie_episode_count or 0

        # Initialize selected options with fallbacks
        self._selected_provider = _selected_provider or getattr(
            arguments, "provider", None
        )
        self._selected_language = _selected_language or getattr(
            arguments, "language", "German Sub"
        )

        # Cache for HTML and other expensive operations
        self._html_cache = html
        self._provider_cache = None
        self._language_cache = None
        self._basic_details_filled = False
        self._full_details_filled = False

        if self.link:
            self._auto_fill_basic_details()
        else:
            self.auto_fill_details()

    @property
    def html(self) -> requests.models.Response:
        """
        Lazy-loaded HTML response for the episode page.

        Returns:
            HTML response object

        Raises:
            requests.RequestException: If HTTP request fails
        """
        if self._html_cache is None:
            if not self.link:
                raise ValueError("Cannot fetch HTML without episode link")

            try:
                self._html_cache = requests.get(
                    self.link,
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                    headers={"User-Agent": RANDOM_USER_AGENT},
                )
                self._html_cache.raise_for_status()
            except requests.RequestException as err:
                logging.error(
                    "Failed to fetch episode HTML for link '%s': %s", self.link, err
                )
                raise

        return self._html_cache

    @lru_cache(maxsize=32)
    def _get_episode_titles_from_html(self) -> Tuple[str, str]:
        """
        Extract German and English episode titles from HTML with caching.

        Returns:
            Tuple of (German Title, English Title)
        """
        try:
            episode_soup = BeautifulSoup(self.html.content, "html.parser")
            
            # --- Method 1: Traditional AniWorld Structure ---
            german_title_div = episode_soup.find("span", class_="episodeGermanTitle")
            english_title_div = episode_soup.find("small", class_="episodeEnglishTitle")

            german_title = ""
            english_title = ""

            if german_title_div:
                german_title = german_title_div.get_text(strip=True)
            if english_title_div:
                english_title = english_title_div.get_text(strip=True)

            # --- Method 2: S.TO New Structure (h2 header) ---
            if not german_title and not english_title:
                # Example: <h2 class="h4 mb-1">S01E01: (Meet The Gallaghers)</h2>
                # Or sometimes just the title.
                h2_title = episode_soup.find("h2", class_="h4 mb-1")
                if h2_title:
                    full_text = h2_title.get_text(strip=True)
                    # Try to remove SxxExx: prefix
                    # Regex to match S\d+E\d+:\s*
                    clean_text = re.sub(r'^S\d+E\d+:\s*', '', full_text).strip()
                    # Remove surrounding parenthesis if present
                    if clean_text.startswith("(") and clean_text.endswith(")"):
                        clean_text = clean_text[1:-1].strip()
                    
                    # Assume this is the English title if only one is present, 
                    # or treat as German if we can't distinguish.
                    # Usually S.TO puts the main title there.
                    english_title = clean_text
                    german_title = clean_text # Fallback to same title

            return german_title, english_title

        except Exception as err:
            logging.error("Error extracting episode titles: %s", err)
            return "", ""

    def _extract_season_from_link(self) -> int:
        """
        Extract season number from episode link.

        Returns:
            Season number (0 for movies)

        Raises:
            ValueError: If season cannot be extracted
        """
        if not self.link:
            raise ValueError("No link provided to extract season from")

        # Check if it's a movie
        if "/filme/" in self.link:
            return 0

        # Extract season from link pattern like /staffel-2/
        try:
            season_part = self.link.split("/")[-2]  # e.g., "staffel-2"
            numbers = re.findall(r"\d+", season_part)

            if numbers:
                return int(numbers[-1])

            raise ValueError(f"No valid season number found in link: {self.link}")

        except (IndexError, ValueError) as err:
            raise ValueError(
                f"Failed to extract season from link '{self.link}': {err}"
            ) from err

    def _extract_episode_from_link(self) -> int:
        """
        Extract episode number from episode link.

        Returns:
            Episode number

        Raises:
            ValueError: If episode cannot be extracted
        """
        if not self.link:
            raise ValueError("No link provided to extract episode from")

        try:
            # Remove trailing slash if present
            link = self.link.rstrip("/")

            # Extract episode from link pattern like /episode-2 or /film-1
            episode_part = link.split("/")[-1]  # e.g., "episode-2" or "film-1"
            numbers = re.findall(r"\d+", episode_part)

            if numbers:
                return int(numbers[-1])

            raise ValueError(f"No valid episode number found in link: {self.link}")

        except (IndexError, ValueError) as err:
            raise ValueError(
                f"Failed to extract episode from link '{self.link}': {err}"
            ) from err

    @lru_cache(maxsize=32)
    def _get_available_languages_from_html(self) -> List[int]:
        """
        Extract available language codes from HTML with caching.

        Language Codes:
            1: German Dub
            2: English Sub
            3: German Sub

        Returns:
            List of available language codes
        """
        try:
            episode_soup = BeautifulSoup(self.html.content, "html.parser")
            language_codes = set()
            
            # --- Method 1: Traditional changeLanguageBox (AniWorld) ---
            change_language_box = episode_soup.find("div", class_="changeLanguageBox")

            if change_language_box:
                img_tags = change_language_box.find_all("img")
                for img in img_tags:
                    lang_key = img.get("data-lang-key")
                    if lang_key and lang_key.isdigit():
                        language_codes.add(int(lang_key))
            
            # --- Method 2: Button-based structure (S.TO) ---
            # If no languages found yet, check for buttons with data-lang-key OR data-language-id
            if not language_codes:
                # Try data-lang-key first
                buttons = episode_soup.find_all("button", attrs={"data-lang-key": True})
                if not buttons:
                    # Try data-language-id
                    buttons = episode_soup.find_all("button", attrs={"data-language-id": True})
                
                for btn in buttons:
                    lang_key = btn.get("data-lang-key")
                    if not lang_key:
                        lang_key = btn.get("data-language-id")
                        
                    if lang_key and lang_key.isdigit():
                        language_codes.add(int(lang_key))

            if not language_codes:
                logging.warning(
                    "No language selection found for episode: %s", self.link
                )
                return []

            return sorted(list(language_codes))

        except Exception as err:
            logging.error("Error extracting language codes: %s", err)
            return []

    @lru_cache(maxsize=32)
    def _get_providers_from_html(self) -> Dict[str, Dict[int, str]]:
        """
        Extract streaming providers from HTML with caching.

        Returns:
            Dictionary mapping provider names to language-URL mappings

        Example:
            {
                'VOE': {1: 'https://aniworld.to/redirect/1766412',
                        2: 'https://aniworld.to/redirect/1766405'},
                'Doodstream': {1: 'https://aniworld.to/redirect/1987922',
                               2: 'https://aniworld.to/redirect/2700342'}
            }

        Raises:
            ValueError: If no providers found
        """
        try:
            soup = BeautifulSoup(self.html.content, "html.parser")
            providers = {}

            # --- Method 1: Traditional List Items (AniWorld) ---
            episode_links = soup.find_all(
                "li", class_=lambda x: x and x.startswith("episodeLink")
            )

            if episode_links:
                for link in episode_links:
                    provider_data = self._extract_provider_data(link)
                    if provider_data:
                        provider_name, lang_key, redirect_url = provider_data

                        if provider_name not in providers:
                            providers[provider_name] = {}

                        providers[provider_name][lang_key] = redirect_url
            
            # --- Method 2: Button-based structure (S.TO) ---
            if not providers:
                # Look for buttons with data-play-url (which contains the redirect path usually encoded/prefixed)
                # In the new S.TO structure, the data-play-url is like /r?t=...
                # And data-provider-name="VOE", data-language-id="2" (or we use data-lang-key if available on button or parent)
                
                # Based on failed_episode.html:
                # <button ... data-play-url="/r?t=..." data-provider-name="VOE" data-lang-key="2" ...>
                # Wait, the HTML showed data-language-id="2". Let's check if there is data-lang-key.
                # In failed_episode.html line 438: data-language-id="2".
                # But my _get_available_languages fix looked for data-lang-key? 
                # Let's check failed_episode.html again.
                # Line 438: data-language-id="2". 
                # But wait, looking at the image inside the button:
                # Code might need to be robust to both. 
                
                buttons = soup.find_all("button", attrs={"data-play-url": True})
                for btn in buttons:
                    provider_name = btn.get("data-provider-name")
                    redirect_path = btn.get("data-play-url")
                    
                    # Try to get language key from data-lang-key OR data-language-id
                    lang_key_str = btn.get("data-lang-key")
                    if not lang_key_str:
                         lang_key_str = btn.get("data-language-id") # S.TO seems to use this
                    
                    if provider_name and redirect_path and lang_key_str and lang_key_str.isdigit():
                        lang_key = int(lang_key_str)
                        redirect_url = f"{self.base_url}{redirect_path}"
                        
                        if provider_name not in providers:
                            providers[provider_name] = {}
                        
                        providers[provider_name][lang_key] = redirect_url

            if not providers:
                raise ValueError(
                    f"No streams available for episode: {self.link}\n"
                    "Try again later or check in the community chat."
                )

            logging.debug(
                'Available providers for "%s":\n%s',
                self.anime_title,
                json.dumps(providers, indent=2),
            )

            return providers

        except Exception as err:
            logging.error("Error extracting providers: %s", err)
            raise

    def _extract_provider_data(self, link_element) -> Optional[Tuple[str, int, str]]:
        """
        Extract provider data from HTML element.

        Args:
            link_element: BeautifulSoup element containing provider data

        Returns:
            Tuple of (provider_name, lang_key, redirect_url) or None
        """
        try:
            # Extract provider name
            provider_name_tag = link_element.find("h4")
            provider_name = (
                provider_name_tag.get_text(strip=True) if provider_name_tag else None
            )

            # Extract redirect link
            redirect_link_tag = link_element.find("a", class_="watchEpisode")
            redirect_path = redirect_link_tag.get("href") if redirect_link_tag else None

            # Extract language key
            lang_key_str = link_element.get("data-lang-key")
            lang_key = (
                int(lang_key_str) if lang_key_str and lang_key_str.isdigit() else None
            )

            # Validate all required data is present
            if provider_name and redirect_path and lang_key:
                redirect_url = f"{self.base_url}{redirect_path}"
                return provider_name, lang_key, redirect_url

            return None

        except (ValueError, AttributeError) as err:
            logging.debug("Failed to extract provider data from element: %s", err)
            return None

    def _get_language_key_from_name(self, language_name: str) -> int:
        """
        Convert language name to language key using site-specific mappings.

        Args:
            language_name: Language name (e.g., "German Dub")

        Returns:
            Language key integer

        Raises:
            ValueError: If language name is invalid
        """
        # Use site-specific language codes
        site_language_codes = SITE_LANGUAGE_CODES.get(self.site)
        language_key = (
            site_language_codes.get(language_name) if site_language_codes else None
        )

        if language_key is None:
            valid_languages = (
                list(site_language_codes.keys()) if site_language_codes else []
            )
            raise ValueError(
                f"Invalid language: {language_name}. Valid options for {self.site}: {valid_languages}"
            )

        return language_key

    def _get_language_names_from_keys(self, language_keys: List[int]) -> List[str]:
        """
        Convert language keys to language names using site-specific mappings.

        Args:
            language_keys: List of language key integers

        Returns:
            List of language names

        Raises:
            ValueError: If any language key is invalid
        """
        # Use site-specific language names
        site_language_names = SITE_LANGUAGE_NAMES.get(self.site)
        language_names = []

        for key in language_keys:
            name = site_language_names.get(key) if site_language_names else None
            if name is None:
                valid_keys = (
                    list(site_language_names.keys()) if site_language_names else []
                )
                raise ValueError(
                    f"Invalid language key: {key} for site: {self.site}. Valid keys: {valid_keys}"
                )
            language_names.append(name)

        return language_names

    def _get_direct_link_from_provider(self) -> str:
        """
        Get direct streaming link from the selected provider.

        Returns:
            Direct streaming link

        Raises:
            ValueError: If provider is not supported or extraction fails
        """
        provider = self._selected_provider

        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provider '{provider}' is currently not supported. "
                f"Supported providers: {SUPPORTED_PROVIDERS}"
            )

        if not self.embeded_link:
            raise ValueError("No embedded link available for direct link extraction")

        try:
            module = importlib.import_module("aniworld.extractors")
            func_name = f"get_direct_link_from_{provider.lower()}"

            if not hasattr(module, func_name):
                raise ValueError(f"Extractor function '{func_name}' not found")

            func = getattr(module, func_name)

            # Prepare kwargs for the extractor function
            kwargs = {f"embeded_{provider.lower()}_link": self.embeded_link}

            # Special case for Luluvdo which needs arguments
            if provider == "Luluvdo":
                kwargs["arguments"] = arguments

            direct_link = func(**kwargs)

            if not direct_link:
                raise ValueError(f"Provider '{provider}' returned empty direct link")

            return direct_link

        except Exception as err:
            logging.error(
                "Error getting direct link from provider '%s': %s", provider, err
            )
            raise ValueError(
                f"Failed to get direct link from provider '{provider}': {err}"
            ) from err

    def get_redirect_link(self) -> Optional[str]:
        """
        Get redirect link for the selected provider and language.

        Returns:
            Redirect link or None if not available
        """
        try:
            # Ensure we have provider data loaded
            self.auto_fill_details()

            lang_key = self._get_language_key_from_name(self._selected_language)

            # Check if selected provider and language combination exists
            if (
                self._selected_provider in self.provider
                and lang_key in self.provider[self._selected_provider]
            ):
                self.redirect_link = self.provider[self._selected_provider][lang_key]
                return self.redirect_link

            # Fallback: find any provider with the selected language
            for provider_name, lang_dict in self.provider.items():
                if lang_key in lang_dict:
                    logging.info(
                        "Switching provider from '%s' to '%s' for language '%s' on site '%s'",
                        self._selected_provider,
                        provider_name,
                        self._selected_language,
                        self.site,
                    )
                    self._selected_provider = provider_name
                    self.redirect_link = lang_dict[lang_key]
                    return self.redirect_link

            # No provider found with selected language
            available_langs = set()
            for lang_dict in self.provider.values():
                available_langs.update(lang_dict.keys())

            # Use site-specific language names for error message
            site_language_names = SITE_LANGUAGE_NAMES.get(self.site)
            available_lang_names = [
                site_language_names.get(key, f"Unknown({key})")
                if site_language_names
                else f"Unknown({key})"
                for key in available_langs
            ]

            logging.warning(
                "No provider found for language '%s' on site '%s'. Available languages: %s",
                self._selected_language,
                self.site,
                available_lang_names,
            )

            self.redirect_link = None
            return None

        except Exception as err:
            logging.error("Error getting redirect link: %s", err)
            self.redirect_link = None
            return None

    def get_embeded_link(self) -> Optional[str]:
        """
        Get embedded streaming link by following the redirect.

        Returns:
            Embedded link or None if unavailable
        """
        if not self.redirect_link:
            self.get_redirect_link()

        if not self.redirect_link:
            logging.warning("No redirect link available for embedded link extraction")
            return None

        try:
            response = requests.get(
                self.redirect_link,
                timeout=DEFAULT_REQUEST_TIMEOUT,
                headers={"User-Agent": RANDOM_USER_AGENT},
                allow_redirects=True,
            )
            response.raise_for_status()

            self.embeded_link = response.url
            return self.embeded_link

        except requests.RequestException as err:
            logging.error(
                "Error getting embedded link from '%s': %s", self.redirect_link, err
            )
            self.embeded_link = None
            return None

    def get_direct_link(
        self, provider: Optional[str] = None, language: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the direct streaming link for the episode.

        Args:
            provider: Provider name to use (overrides selected provider)
            language: Language to use (overrides selected language)

        Returns:
            Direct streaming link or None if unavailable

        Example:
            episode.get_direct_link("VOE", "German Sub")
        """
        # Update selected options if provided
        if provider:
            self._selected_provider = provider

        if language:
            self._selected_language = language

        # Validate selected provider
        if self._selected_provider not in SUPPORTED_PROVIDERS:
            logging.error("Provider '%s' is not supported", self._selected_provider)
            return None

        try:
            # Get embedded link if not already available
            if not self.embeded_link:
                if not self.get_embeded_link():
                    logging.error("Failed to get embedded link")
                    return None

            # Get direct link from provider
            self.direct_link = self._get_direct_link_from_provider()
            return self.direct_link

        except Exception as err:
            logging.error("Error getting direct link: %s", err)
            self.direct_link = None
            return None

    def _get_preview_image_link_from_provider(self) -> str:
        """
        Get preview image link from the given provider.

        Args:
            provider: Provider name

        Returns:
            Preview image link

        Raises:
            ValueError: If provider is not supported or extraction fails
        """

        provider = self._selected_provider

        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provider '{provider}' is currently not supported. "
                f"Supported providers: {SUPPORTED_PROVIDERS}"
            )

        if not self.embeded_link:
            raise ValueError("No embedded link available for preview image extraction")

        try:
            module = importlib.import_module("aniworld.extractors")
            func_name = f"get_preview_image_link_from_{provider.lower()}"

            if not hasattr(module, func_name):
                raise ValueError(f"Preview extractor function '{func_name}' not found")

            func = getattr(module, func_name)

            # Prepare kwargs for the extractor function
            kwargs = {f"embeded_{provider.lower()}_link": self.embeded_link}
            return func(**kwargs)

        except Exception as err:
            raise ValueError(
                f"Failed to get preview image from provider '{provider}': {err}"
            ) from err

    def get_preview_image_link(self, provider: Optional[str] = None) -> Optional[str]:
        """
        Get the preview image link for the episode.

        Args:
            provider: Provider name to use (overrides selected provider)

        Returns:
            Preview image link or None if unavailable
        """
        # Override provider if passed
        if provider:
            self._selected_provider = provider
            lang_key = next(iter(self.provider.get(provider, {})), None)
            if lang_key is not None:
                lang_name = self._get_language_names_from_keys([lang_key])[0]
                self._selected_language = lang_name

        # Validate provider
        if self._selected_provider not in SUPPORTED_PROVIDERS:
            logging.error("Provider '%s' is not supported", self._selected_provider)
            return None

        try:
            # Ensure embedded link is available
            if not self.embeded_link:
                if not self.get_embeded_link():
                    logging.error("Failed to get embedded link")
                    return None

            # Extract preview image
            preview_link = self._get_preview_image_link_from_provider()

            if not preview_link:
                logging.warning(
                    "No preview image found from provider '%s'", self._selected_provider
                )
                return None

            return preview_link

        except Exception as err:
            logging.error(
                "Error getting preview image from provider '%s': %s",
                self._selected_provider,
                err,
            )
            return None

    def _auto_fill_basic_details(self) -> None:
        """
        Fill only essential details needed for link construction without expensive operations.
        """
        if self._basic_details_filled:
            return

        try:
            # Construct link if missing but have components
            if (
                not self.link
                and self.slug
                and self.season is not None
                and self.episode is not None
            ):
                if self.season == 0:  # Movie
                    self.link = (
                        f"{self.base_url}/{self.stream_path}/{self.slug}/filme/"
                        f"film-{self.episode}"
                    )
                else:  # Regular episode
                    self.link = (
                        f"{self.base_url}/{self.stream_path}/{self.slug}/"
                        f"staffel-{self.season}/episode-{self.episode}"
                    )

            # Extract components from link if missing (no HTTP requests)
            if self.link:
                if not self.slug:
                    try:
                        self.slug = self.link.split("/")[-3]
                    except IndexError:
                        logging.warning(
                            "Could not extract slug from link: %s", self.link
                        )

                if self.season is None:
                    try:
                        self.season = self._extract_season_from_link()
                    except ValueError as err:
                        logging.warning("Could not extract season: %s", err)

                if self.episode is None:
                    try:
                        self.episode = self._extract_episode_from_link()
                    except ValueError as err:
                        logging.warning("Could not extract episode: %s", err)

            self._basic_details_filled = True

        except Exception as err:
            logging.error("Critical error in _auto_fill_basic_details: %s", err)
            self._basic_details_filled = True

    def auto_fill_details(self) -> None:
        """
        Automatically fill episode details from available information.
        This is now called lazily only when needed.
        """
        if self._full_details_filled:
            return

        try:
            # First ensure basic details are filled
            self._auto_fill_basic_details()

            # Fetch and populate metadata if link is available (expensive operations)
            if self.link:
                try:
                    # Get anime title if missing
                    if not self.anime_title:
                        self.anime_title = get_anime_title_from_html(
                            self.html, self.site
                        )

                    # Get episode titles if missing
                    if not self.title_german and not self.title_english:
                        self.title_german, self.title_english = (
                            self._get_episode_titles_from_html()
                        )

                    # Get available languages
                    if not self.language:
                        self.language = self._get_available_languages_from_html()

                    # Get language names
                    if not self.language_name and self.language:
                        self.language_name = self._get_language_names_from_keys(
                            self.language
                        )

                    # Get providers
                    if not self.provider:
                        self.provider = self._get_providers_from_html()

                    # Get provider names
                    if not self.provider_name and self.provider:
                        self.provider_name = list(self.provider.keys())

                except Exception as err:
                    logging.error("Error auto-filling episode details: %s", err)

            self._full_details_filled = True

        except Exception as err:
            logging.error("Critical error in auto_fill_details: %s", err)
            self._full_details_filled = True

    def validate_configuration(self) -> List[str]:
        """
        Validate episode configuration and return any issues.

        Returns:
            List of validation error messages
        """
        issues = []

        if not self.link and (
            not self.slug or self.season is None or self.episode is None
        ):
            issues.append("Either 'link' or 'slug + season + episode' must be provided")

        if self.site not in SUPPORTED_SITES:
            issues.append(f"Unsupported site: {self.site}")

        # Use site-specific language codes for validation
        site_language_codes = SITE_LANGUAGE_CODES.get(self.site)
        if (
            not site_language_codes
            or self._selected_language not in site_language_codes
        ):
            valid_languages = (
                list(site_language_codes.keys()) if site_language_codes else []
            )
            issues.append(
                f"Invalid selected language: {self._selected_language} for site: {self.site}. Valid options: {valid_languages}"
            )

        if (
            self._selected_provider
            and self._selected_provider not in SUPPORTED_PROVIDERS
        ):
            issues.append(f"Unsupported provider: {self._selected_provider}")

        return issues

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert episode to dictionary representation.

        Returns:
            Dictionary with episode data
        """
        return {
            "anime_title": self.anime_title,
            "title_german": self.title_german,
            "title_english": self.title_english,
            "season": self.season,
            "episode": self.episode,
            "slug": self.slug,
            "site": self.site,
            "link": self.link,
            "mal_id": self.mal_id,
            "redirect_link": self.redirect_link,
            "embeded_link": self.embeded_link,
            "direct_link": self.direct_link,
            "provider_count": len(self.provider) if self.provider else 0,
            "provider_names": self.provider_name,
            "language_codes": self.language,
            "language_names": self.language_name,
            "selected_provider": self._selected_provider,
            "selected_language": self._selected_language,
            "season_episode_count": self.season_episode_count,
            "movie_episode_count": self.movie_episode_count,
        }

    def to_json(self) -> str:
        """
        Convert episode to JSON string representation.

        Returns:
            JSON string with episode data
        """
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def __str__(self) -> str:
        """String representation of episode."""
        return (
            f"Episode(anime='{self.anime_title}', S{self.season:02d}E{self.episode:02d}, "
            f"provider='{self._selected_provider}', language='{self._selected_language}')"
        )

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        return (
            f"Episode(anime_title='{self.anime_title}', season={self.season}, "
            f"episode={self.episode}, slug='{self.slug}', "
            f"selected_provider='{self._selected_provider}', "
            f"selected_language='{self._selected_language}')"
        )


def get_anime_title_from_html(
    html: requests.models.Response, site: str = "aniworld.to"
) -> str:
    """
    Extract anime title from HTML response with site-specific parsing.

    Args:
        html: HTTP response object containing the page HTML
        site: The streaming site being used for parsing adjustments

    Returns:
        Anime title string or empty string if not found
    """
    try:
        soup = BeautifulSoup(html.content, "html.parser")

        title_div = None
        # Site-specific title extraction
        if site == S_TO or site == "s.to":
            # S_TO uses: <div class="series-title"><h1><span>Title</span></h1>...</div>
            title_div = soup.find("div", class_="series-title")
            if title_div:
                title_span = title_div.find("h1")
                if title_span:
                    span_element = title_span.find("span")
                    if span_element:
                        return span_element.get_text(strip=True)
                    return title_span.get_text(strip=True)
                return title_div.get_text(strip=True)
        else:  # aniworld.to (default)
            title_div = soup.find("div", class_="series-title")

        if title_div:
            # Try different title extraction methods
            title_span = title_div.find("h1")
            if title_span:
                span_element = title_span.find("span")
                if span_element:
                    return span_element.get_text(strip=True)
                return title_span.get_text(strip=True)

            # Fallback to div text
            return title_div.get_text(strip=True)
            
        # Fallback for new designs (e.g. S.TO 2024 update)
        # Example: <h1 class="h2 fw-bold mb-1">Shameless UK</h1>
        h1_title = soup.find("h1", class_="h2")
        if h1_title:
                return h1_title.get_text(strip=True)
        
        # Last resort: Parse from <title> tag
        # Example: <title>Shameless UK S01E01 | S.to</title>
        if soup.title:
            title_text = soup.title.get_text(strip=True)
            # Remove suffix " | S.to"
            if " | " in title_text:
                title_text = title_text.split(" | ")[0]
            # Remove " SxxExx" suffix if present (e.g. Shameless UK S01E01)
            title_text = re.sub(r' S\d+E\d+.*', '', title_text).strip()
            return title_text

        return ""

    except Exception as err:
        logging.error("Error extracting anime title from %s: %s", site, err)
        return ""


if __name__ == "__main__":
    pass
