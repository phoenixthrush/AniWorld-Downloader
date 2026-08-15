import re
import shutil
import zipfile
from os import getenv
from pathlib import Path
from pprint import pprint
from urllib.parse import quote, urlparse

from ...config import GLOBAL_SESSION
from ...playwright.captcha import is_captcha_page, solve_captcha
from .vrf import sign_url

SEARCH_API = "https://mangafire.to/api/titles?keyword={}&limit=20"
CHAPTERS_API = "https://mangafire.to/api/titles/{}/chapters?language=en&sort=number&order=asc&page={}&limit=200"
CHAPTER_URL = "https://mangafire.to/title/{}/chapter/{}"
CHAPTER_API = "https://mangafire.to/api/chapters/{}"

HEADERS = {"Referer": "https://mangafire.to/"}


# -----------------------------
# helpers
# -----------------------------


def _safe_name(value: str) -> str:
    """Return a filesystem-safe name."""
    cleaned = "".join(char for char in value if char not in '<>:"/\\|?*').strip()
    return cleaned or "untitled"


def _file_suffix_from_url(url: str) -> str:
    """Return the file suffix from a url."""
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix or ".jpg"


def _get(url: str, timeout=None):
    """Send a get request."""
    request_url = sign_url(url) if url.startswith("https://mangafire.to/api/") else url
    response = GLOBAL_SESSION.get(request_url, headers=HEADERS, timeout=timeout)
    if url.startswith("https://mangafire.to/") and is_captcha_page(
        response.text or "", response.status_code
    ):
        solve_captcha(request_url)
        response = GLOBAL_SESSION.get(request_url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def _get_download_root() -> Path:
    """Return the download root path."""
    value = getenv("ANIWORLD_DOWNLOAD_PATH", "Downloads").strip()

    if not value:
        value = "Downloads"

    path = Path(value).expanduser()

    if path.is_absolute():
        return path

    return Path.home() / path


def _download_file(url: str, file_path: Path) -> Path:
    """Download a file to disk."""
    file_path.parent.mkdir(parents=True, exist_ok=True)

    response = _get(url)

    with file_path.open("wb") as file:
        file.write(response.content)

    return file_path


def _strip_html(value: str) -> str:
    """Return a plain-text version of a HTML fragment."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------
# image
# -----------------------------


class MangaFireToImage:
    """Store MangaFire image data."""

    def __init__(self, image_url: str, width: int, height: int):
        """Set up the image."""
        self.image_url = image_url
        self.width = width
        self.height = height

    def __str__(self) -> str:
        """Return a readable image string."""
        return self.image_url

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return f"Image({self.width}x{self.height})"

    @property
    def file_suffix(self) -> str:
        """Return the image file suffix."""
        return _file_suffix_from_url(self.image_url)

    def download(self, file_path: str | Path) -> Path:
        """Download the image to disk."""
        return _download_file(self.image_url, Path(file_path))


# -----------------------------
# page
# -----------------------------


class MangaFireToPage:
    """Store MangaFire page data."""

    def __init__(
        self,
        chapter,
        page_number: int,
        image_url: str,
        width: int,
        height: int,
    ):
        """Set up the page."""
        self.chapter = chapter
        self.page_number = page_number
        self.image = MangaFireToImage(
            image_url=image_url,
            width=width,
            height=height,
        )

    def __str__(self) -> str:
        """Return a readable page string."""
        return f"Page {self.page_number}"

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    @property
    def image_url(self) -> str:
        """Return the page image url."""
        return self.image.image_url

    @property
    def file_name(self) -> str:
        """Return the default file name."""
        return f"{self.page_number:03}{self.image.file_suffix}"

    def download(self, folder: str | Path | None = None, total_pages: int = 0) -> Path:
        """Download the page image."""
        if folder is None:
            folder = (
                _get_download_root()
                / _safe_name(self.chapter.series.title)
                / self.chapter.folder_name
            )
        else:
            folder = Path(folder)

        file_path = folder / self.file_name
        progress = (
            f"{self.page_number:03}/{total_pages:03}"
            if total_pages
            else f"{self.page_number:03}"
        )

        if file_path.exists():
            print(f"[SKIP] {progress} {file_path}")
            return file_path

        print(f"[DOWN] {progress} {file_path}")
        return self.image.download(file_path)


# -----------------------------
# chapter
# -----------------------------


class MangaFireToChapter:
    """Store MangaFire chapter data."""

    def __init__(
        self,
        url: str,
        series=None,
        chapter_id: int | None = None,
        chapter_number: float | None = None,
        chapter_name: str = "",
        chapter_language: str = "",
        chapter_type: str = "",
        created_at: int = 0,
        selected_path=None,
        selected_language=None,
        selected_provider=None,
        selected_pages: list[int] | None = None,
        format: str = "",
    ):
        """Set up the chapter."""
        self.mangafire_format = (
            format.strip().lower() or getenv("MANGAFIRE_FORMAT", "jpg").strip().lower()
        )
        self._series = series
        self.chapter_url = url
        self.chapter_id = chapter_id
        self.chapter_number = chapter_number
        self.chapter_name = chapter_name
        self.chapter_language = chapter_language
        self.chapter_type = chapter_type
        self.created_at = created_at

        self.__selected_path_param = selected_path
        self.__selected_language_param = selected_language
        self.__selected_provider_param = selected_provider
        self.__selected_pages_param = selected_pages

        self.chapter_api_url = CHAPTER_API.format(chapter_id or 0)

        self.__chapter_data = None
        self.__pages = None

        if self.chapter_number is None:
            self.chapter_number = self.__extract_chapter_number_from_url(url)

        self.__load_metadata_from_series()
        self.chapter_api_url = CHAPTER_API.format(self.chapter_id or 0)

    def __str__(self) -> str:
        """Return a readable chapter string."""
        if self.chapter_name:
            return f"Chapter {self.chapter_number} - {self.chapter_name}"
        return f"Chapter {self.chapter_number}"

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    def __extract_chapter_number_from_url(self, chapter_url: str):
        """Return the chapter number encoded in a MangaFire chapter url."""
        chapter_part = chapter_url.rstrip("/").rsplit("/chapter/", 1)[-1]
        try:
            value = float(chapter_part)
        except ValueError:
            return chapter_part
        return int(value) if value.is_integer() else value

    def __load_metadata_from_series(self) -> None:
        """Fill chapter metadata from the parent series when possible."""
        if self.chapter_id and self.chapter_number is not None:
            return

        try:
            chapters = getattr(self.series, "chapters", []) or []
        except Exception:
            chapters = []

        for chapter in chapters:
            if getattr(chapter, "chapter_url", "") == self.chapter_url:
                self.chapter_id = getattr(chapter, "chapter_id", self.chapter_id)
                self.chapter_number = getattr(
                    chapter, "chapter_number", self.chapter_number
                )
                self.chapter_name = self.chapter_name or getattr(
                    chapter, "chapter_name", ""
                )
                self.chapter_language = self.chapter_language or getattr(
                    chapter, "chapter_language", ""
                )
                self.chapter_type = self.chapter_type or getattr(
                    chapter, "chapter_type", ""
                )
                self.created_at = self.created_at or getattr(chapter, "created_at", 0)
                break

    @property
    def chapter_data(self) -> dict:
        """Return the chapter data."""
        if self.__chapter_data is None:
            if not self.chapter_id:
                self.__load_metadata_from_series()
                self.chapter_api_url = CHAPTER_API.format(self.chapter_id or 0)
            response = _get(self.chapter_api_url)
            self.__chapter_data = response.json().get("data", {})
        return self.__chapter_data

    @property
    def pages(self) -> list:
        """Return chapter page objects."""
        if self.__pages is None:
            self.__pages = []

            for index, page in enumerate(self.chapter_data.get("pages", []), start=1):
                self.__pages.append(
                    MangaFireToPage(
                        chapter=self,
                        page_number=index,
                        image_url=page["url"],
                        width=page.get("width", 0),
                        height=page.get("height", 0),
                    )
                )

        return self.__pages

    @property
    def images(self) -> list:
        """Return page images."""
        return [page.image for page in self.pages]

    @property
    def folder_name(self) -> str:
        """Return the chapter folder name."""
        base = f"Chapter {self.chapter_number}"
        if self.chapter_name:
            base += f" - {self.chapter_name}"
        return _safe_name(base)

    @property
    def season_number(self):
        """Return a chapter number for web UI compatibility."""
        return self.chapter_number

    @property
    def episode_number(self):
        """Return a chapter number for episode-style UIs."""
        return self.chapter_number

    @property
    def episode_count(self) -> int:
        """Return one selectable item per chapter."""
        return 1

    @property
    def are_movies(self) -> bool:
        """MangaFire chapters are not movies."""
        return False

    @property
    def title_en(self) -> str:
        """Return the English title label for the chapter."""
        return self.chapter_name or f"Chapter {self.chapter_number}"

    @property
    def title_de(self) -> str:
        """Return the German title label for the chapter."""
        return self.title_en

    @property
    def episodes(self) -> list:
        """Return this chapter as the only selectable unit."""
        return [self]

    @property
    def selected_path(self):
        """Return the explicitly selected download path, if any."""
        return self.__selected_path_param

    @property
    def selected_language(self):
        """Return the selected language label, if any."""
        return self.__selected_language_param

    @property
    def selected_provider(self):
        """Return the selected provider label, if any."""
        return self.__selected_provider_param

    @property
    def selected_pages(self):
        """Return selected page numbers, if any."""
        return self.__selected_pages_param

    @property
    def series(self):
        """Return the parent series."""
        if self._series is None:
            series_url = self.chapter_url.rsplit("/chapter/", 1)[0]
            self._series = MangaFireToSeries(series_url=series_url)
        return self._series

    @property
    def url(self) -> str:
        """Return the canonical chapter url."""
        return self.chapter_url

    def download(
        self,
        folder: str | Path | None = None,
        chapter_index: int = 0,
        total_chapters: int = 0,
    ) -> Path:
        """Download all chapter pages as a .cbz file."""
        chapter_title = (
            getattr(self._series, "title", "")
            if self._series is not None
            else self.chapter_name or f"Chapter {self.chapter_number}"
        )
        if folder is None:
            if self.selected_path:
                folder = (
                    Path(self.selected_path)
                    / _safe_name(chapter_title)
                    / self.folder_name
                )
            else:
                folder = (
                    _get_download_root() / _safe_name(chapter_title) / self.folder_name
                )
        else:
            folder = Path(folder)

        cbz_path = folder.with_suffix(".cbz")

        chapter_progress = (
            f"{chapter_index:03}/{total_chapters:03}"
            if chapter_index and total_chapters
            else "---/---"
        )

        pages = self.pages
        if self.selected_pages is not None:
            selected = {int(page_number) for page_number in self.selected_pages}
            pages = [page for page in pages if page.page_number in selected]

        total_pages = len(pages)

        if self.mangafire_format != "cbz":
            folder.mkdir(parents=True, exist_ok=True)
            print(f"[{chapter_progress}] {self}")
            for page in pages:
                page.download(folder, total_pages=total_pages)
            return folder

        existing_files = set()
        if cbz_path.exists():
            try:
                with zipfile.ZipFile(cbz_path, "r") as zf:
                    existing_files = set(zf.namelist())
            except zipfile.BadZipFile:
                pass

        pages_to_download = [p for p in pages if p.file_name not in existing_files]

        if not pages_to_download:
            print(
                f"[SKIP] [{chapter_progress}] {cbz_path.name} (all selected pages already in archive)"
            )
            return cbz_path

        folder.mkdir(parents=True, exist_ok=True)
        print(f"[{chapter_progress}] {self}")

        for page in pages_to_download:
            page.download(folder, total_pages=total_pages)

        print(f"[ZIP] Updating {cbz_path.name}...")
        with zipfile.ZipFile(cbz_path, "a", zipfile.ZIP_DEFLATED) as zf:
            for page in pages_to_download:
                file_path = folder / page.file_name
                if file_path.exists():
                    zf.write(file_path, arcname=page.file_name)

        shutil.rmtree(folder, ignore_errors=True)

        return cbz_path

    def debug_pages(self) -> None:
        """Print raw chapter data."""
        pprint(self.chapter_data)


# -----------------------------
# series
# -----------------------------


class MangaFireToSeries:
    """Store MangaFire series data."""

    def __init__(self, series_url: str | None = None, url: str | None = None):
        """Set up the series."""
        if series_url is None:
            series_url = url
        if not series_url:
            raise ValueError("series_url is required")

        self.series_url = series_url

        self.__series_item = None
        self.__chapters_data = None
        self.__chapters = None
        self.__poster_url = ""
        self.__description = ""
        self.__genres = []
        self.__release_year = ""
        self.__series_data = None

        self.__load_from_series_url(series_url)

    def __load_from_series_url(self, series_url: str) -> None:
        """Load series data from a MangaFire title url."""
        slug_part = series_url.rstrip("/").split("/title/")[-1]
        self.__series_item = {
            "hid": slug_part.split("-")[0],
            "slug": "-".join(slug_part.split("-")[1:]),
            "title": slug_part.split("-", 1)[1].replace("-", " ").title(),
        }

    def __load_series_metadata(self) -> None:
        """Load title metadata from MangaFire's title detail API."""
        if self.__series_data is not None:
            return

        response = _get(f"https://mangafire.to/api/titles/{self.hid}")
        payload = response.json().get("data", {})
        self.__series_data = payload

        title = payload.get("title")
        if title:
            self.__series_item["title"] = title

        poster = payload.get("poster") or {}
        self.__poster_url = (
            poster.get("large")
            or poster.get("medium")
            or poster.get("small")
            or self.__poster_url
        )

        synopsis = payload.get("synopsisHtml") or payload.get("synopsis") or ""
        self.__description = _strip_html(synopsis)

        genres = payload.get("genres") or []
        self.__genres = [item.get("title", "") for item in genres if item.get("title")]

        year = payload.get("year")
        self.__release_year = str(year) if year else ""

    def __str__(self) -> str:
        """Return a readable series string."""
        return self.title

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    # -----------------------------
    # series fields
    # -----------------------------

    @property
    def series_item(self) -> dict:
        """Return the raw series item."""
        return self.__series_item

    @property
    def hid(self) -> str:
        """Return the series hid."""
        return self.series_item["hid"]

    @property
    def slug(self) -> str:
        """Return the series slug."""
        return self.series_item["slug"]

    @property
    def title(self) -> str:
        """Return the series title."""
        if self.__series_data is None:
            self.__load_series_metadata()
        return self.series_item["title"]

    @property
    def title_cleaned(self) -> str:
        """Return a filesystem-safe title for folder matching."""
        return _safe_name(self.title)

    @property
    def poster_url(self) -> str:
        """Return the series poster url when available."""
        if self.__series_data is None:
            self.__load_series_metadata()
        return self.__poster_url

    @property
    def description(self) -> str:
        """Return the series description when available."""
        if self.__series_data is None:
            self.__load_series_metadata()
        return self.__description

    @property
    def genres(self) -> list:
        """Return the series genres when available."""
        if self.__series_data is None:
            self.__load_series_metadata()
        return self.__genres

    @property
    def release_year(self) -> str:
        """Return the release year when available."""
        if self.__series_data is None:
            self.__load_series_metadata()
        return self.__release_year

    # -----------------------------
    # chapters
    # -----------------------------

    @property
    def chapters_api_url(self) -> str:
        """Return the chapters API url."""
        return CHAPTERS_API.format(self.hid, 1)

    @property
    def chapters_data(self) -> dict:
        """Return raw chapter data."""
        if self.__chapters_data is None:
            chapters_data = {}
            items = []
            seen = set()
            page = 1

            while True:
                payload = _get(CHAPTERS_API.format(self.hid, page)).json()
                if page == 1:
                    chapters_data = payload

                new_items = [
                    item for item in payload.get("items", []) if item["id"] not in seen
                ]
                if not new_items:
                    break

                items.extend(new_items)
                seen.update(item["id"] for item in new_items)
                page += 1

            chapters_data["items"] = items
            self.__chapters_data = chapters_data
        return self.__chapters_data

    @property
    def chapters(self) -> list:
        """Return all chapter objects."""
        if self.__chapters is None:
            self.__chapters = []

            for item in self.chapters_data.get("items", []):
                chapter_url = CHAPTER_URL.format(self.hid, item["number"])
                self.__chapters.append(
                    MangaFireToChapter(
                        url=chapter_url,
                        series=self,
                        chapter_id=item["id"],
                        chapter_number=item["number"],
                        chapter_name=item["name"],
                        chapter_language=item["language"],
                        chapter_type=item["type"],
                        created_at=item["createdAt"],
                    )
                )

        return self.__chapters

    @property
    def seasons(self) -> list:
        """Return chapter objects in a season-like shape for the web UI."""
        return self.chapters

    @property
    def official_chapters(self) -> list:
        """Return official chapters."""
        return [
            chapter for chapter in self.chapters if chapter.chapter_type == "official"
        ]

    @property
    def unofficial_chapters(self) -> list:
        """Return unofficial chapters."""
        return [
            chapter for chapter in self.chapters if chapter.chapter_type == "unofficial"
        ]

    @property
    def preferred_chapters(self) -> list:
        """Return official chapters if available, else unofficial chapters."""
        return self.official_chapters or self.unofficial_chapters

    def download(
        self,
        folder: str | Path | None = None,
        chapters: list | None = None,
    ) -> Path:
        """Download a set of chapters."""
        if folder is None:
            folder = _get_download_root() / _safe_name(self.title)
        else:
            folder = Path(folder)

        folder.mkdir(parents=True, exist_ok=True)

        selected_chapters = chapters or self.preferred_chapters
        total_chapters = len(selected_chapters)

        for index, chapter in enumerate(selected_chapters, start=1):
            chapter_folder = folder / chapter.folder_name
            chapter.download(
                chapter_folder,
                chapter_index=index,
                total_chapters=total_chapters,
            )

        return folder


# -----------------------------
# search
# -----------------------------


def search_series(query: str) -> list:
    """Search MangaFire series."""
    response = _get(SEARCH_API.format(quote(query)))
    response_data = response.json()
    return response_data.get("items", [])


# -----------------------------
# example
# -----------------------------


if __name__ == "__main__":
    # query = "darling in the franxx"
    # results = search_series(query)

    # if not results:
    #    raise ValueError(f"No series found for query: {query}")

    # first_item = results[0]
    # series_url = f"https://mangafire.to{first_item['url']}"
    # series = MangaFireToSeries(series_url=series_url)

    series = MangaFireToSeries(
        series_url="https://mangafire.to/title/zlwvm-darling-in-the-franxx"
    )

    print(series)
    print()

    print("preferred chapters:")
    for item in series.preferred_chapters[:5]:
        print("-", item)

    print()
    first_chapter = series.preferred_chapters[0]

    print("page count:")
    print(len(first_chapter.pages))

    print()
    print("pages:")
    for page in first_chapter.pages:
        print("-", page, page.image_url)

    # print()
    # print("raw chapter data:")
    # first_chapter.debug_pages()

    series.download()
