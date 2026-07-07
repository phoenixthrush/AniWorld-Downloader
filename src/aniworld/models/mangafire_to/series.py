from urllib.parse import quote

import niquests

SEARCH_API = "https://mangafire.to/api/titles?keyword={}&limit=20"
CHAPTERS_API = "https://mangafire.to/api/titles/{}/chapters?language=en&sort=number&order=asc&page=1&limit=200"
CHAPTER_URL = "https://mangafire.to/title/{}/chapter/{}"
CHAPTER_API = "https://mangafire.to/api/chapters/{}"


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
        self.__images = None

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
            response = niquests.get(self.chapter_api_url)
            self.__chapter_data = response.json().get("data", {})
        return self.__chapter_data

    @property
    def images(self) -> list:
        """Return chapter image objects."""
        if self.__images is None:
            self.__images = []

            for page in self.chapter_data.get("pages", []):
                self.__images.append(
                    MangaFireToImage(
                        image_url=page["url"],
                        width=page["width"],
                        height=page["height"],
                    )
                )

        return self.__images


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
            response = niquests.get(self.chapters_api_url)
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


def search_series(query: str) -> list:
    """Search MangaFire series."""
    response = niquests.get(SEARCH_API.format(quote(query)))
    response_data = response.json()
    return response_data.get("items", [])


if __name__ == "__main__":
    query = "darling in the franxx"
    results = search_series(query)

    if not results:
        raise ValueError(f"No series found for query: {query}")

    first_item = results[0]
    series_url = f"https://mangafire.to{first_item['url']}"

    series = MangaFireToSeries(series_url=series_url)

    print(series)
    print()

    print("search results:")
    for item in results:
        poster_url = item.get("poster", {}).get("large")
        print("-", item["title"], item["url"], poster_url)

    print()
    print("preferred chapters:")
    for chapter in series.preferred_chapters[:5]:
        print("-", chapter)

    print()
    chapter = series.preferred_chapters[0]
    print("selected chapter:")
    print(chapter)

    print()
    print("images:")
    for image in chapter.images:
        print("-", image.image_url)

    print()
    image = chapter.images[0]
    print("selected image:")
    print(image.image_url)
