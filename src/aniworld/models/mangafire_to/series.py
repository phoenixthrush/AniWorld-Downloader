from os import getenv
from pathlib import Path
from pprint import pprint
from urllib.parse import quote, urlparse

import niquests

SEARCH_API = "https://mangafire.to/api/titles?keyword={}&limit=20"
CHAPTERS_API = "https://mangafire.to/api/titles/{}/chapters?language=en&sort=number&order=asc&page=1&limit=200"
CHAPTER_URL = "https://mangafire.to/title/{}/chapter/{}"
CHAPTER_API = "https://mangafire.to/api/chapters/{}"

SESSION = niquests.Session()


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


def _get(url: str):
    """Send a get request."""
    response = SESSION.get(url)
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
        series,
        chapter_id: int,
        chapter_number: float,
        chapter_name: str = "",
        chapter_language: str = "",
        chapter_type: str = "",
        created_at: int = 0,
    ):
        """Set up the chapter."""
        self.series = series
        self.chapter_id = chapter_id
        self.chapter_number = chapter_number
        self.chapter_name = chapter_name
        self.chapter_language = chapter_language
        self.chapter_type = chapter_type
        self.created_at = created_at

        self.chapter_url = CHAPTER_URL.format(series.hid, chapter_number)
        self.chapter_api_url = CHAPTER_API.format(chapter_id)

        self.__chapter_data = None
        self.__pages = None

    def __str__(self) -> str:
        """Return a readable chapter string."""
        if self.chapter_name:
            return f"Chapter {self.chapter_number} - {self.chapter_name}"
        return f"Chapter {self.chapter_number}"

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    @property
    def chapter_data(self) -> dict:
        """Return the chapter data."""
        if self.__chapter_data is None:
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

    def download(
        self,
        folder: str | Path | None = None,
        chapter_index: int = 0,
        total_chapters: int = 0,
    ) -> Path:
        """Download all chapter pages."""
        if folder is None:
            folder = (
                _get_download_root() / _safe_name(self.series.title) / self.folder_name
            )
        else:
            folder = Path(folder)

        folder.mkdir(parents=True, exist_ok=True)

        chapter_progress = (
            f"{chapter_index:03}/{total_chapters:03}"
            if chapter_index and total_chapters
            else "---/---"
        )

        print(f"[{chapter_progress}] {self}")

        total_pages = len(self.pages)

        for page in self.pages:
            page.download(folder, total_pages=total_pages)

        return folder

    def debug_pages(self) -> None:
        """Print raw chapter data."""
        pprint(self.chapter_data)


# -----------------------------
# series
# -----------------------------


class MangaFireToSeries:
    """Store MangaFire series data."""

    def __init__(self, series_url: str):
        """Set up the series."""
        self.series_url = series_url

        self.__series_item = None
        self.__chapters_data = None
        self.__chapters = None

        self.__load_from_series_url(series_url)

    def __load_from_series_url(self, series_url: str) -> None:
        """Load series data from a MangaFire title url."""
        slug_part = series_url.rstrip("/").split("/title/")[-1]
        self.__series_item = {
            "hid": slug_part.split("-")[0],
            "slug": "-".join(slug_part.split("-")[1:]),
            "title": slug_part.split("-", 1)[1].replace("-", " ").title(),
        }

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
        return self.series_item["title"]

    # -----------------------------
    # chapters
    # -----------------------------

    @property
    def chapters_api_url(self) -> str:
        """Return the chapters API url."""
        return CHAPTERS_API.format(self.hid)

    @property
    def chapters_data(self) -> dict:
        """Return raw chapter data."""
        if self.__chapters_data is None:
            response = _get(self.chapters_api_url)
            self.__chapters_data = response.json()
        return self.__chapters_data

    @property
    def chapters(self) -> list:
        """Return all chapter objects."""
        if self.__chapters is None:
            self.__chapters = []

            for item in self.chapters_data.get("items", []):
                self.__chapters.append(
                    MangaFireToChapter(
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
