from urllib.parse import quote

import niquests

SEARCH_API = "https://mangafire.to/api/titles?keyword={}&limit=1"
CHAPTERS_API = "https://mangafire.to/api/titles/{}/chapters?language=en&sort=number&order=asc&page=1&limit=200"
CHAPTER_URL = "https://mangafire.to/title/{}/chapter/{}"
CHAPTER_API = "https://mangafire.to/api/chapters/{}"


class MangaFireToImage:
    """Store MangaFire image data."""

    def __init__(self, url: str, width: int, height: int):
        """Set up the image."""
        self.url = url
        self.width = width
        self.height = height

    def __str__(self) -> str:
        """Return a readable image string."""
        return self.url

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return f"Image({self.width}x{self.height})"


class MangaFireToChapter:
    """Store MangaFire chapter data."""

    def __init__(
        self,
        series,
        chapter_id: int,
        number: float,
        name: str = "",
        language: str = "",
        chapter_type: str = "",
        created_at: int = 0,
    ):
        """Set up the chapter."""
        self.series = series
        self.id = chapter_id
        self.number = number
        self.name = name
        self.language = language
        self.type = chapter_type
        self.created_at = created_at

        self.url = CHAPTER_URL.format(series.hid, number)
        self.api_url = CHAPTER_API.format(chapter_id)

        self.__data = None
        self.__images = None

    def __str__(self) -> str:
        """Return a readable chapter string."""
        if self.name:
            return f"Chapter {self.number} - {self.name}"
        return f"Chapter {self.number}"

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    @property
    def data(self) -> dict:
        """Return the chapter data."""
        if self.__data is None:
            resp = niquests.get(self.api_url)
            self.__data = resp.json().get("data", {})
        return self.__data

    @property
    def images(self) -> list:
        """Return chapter image objects."""
        if self.__images is None:
            self.__images = []

            for page in self.data.get("pages", []):
                self.__images.append(
                    MangaFireToImage(
                        url=page["url"],
                        width=page["width"],
                        height=page["height"],
                    )
                )

        return self.__images


class MangaFireToSeries:
    """Store MangaFire series data."""

    def __init__(self, query: str | None = None, url: str | None = None):
        """Set up the series."""
        self.query = query
        self._url = url

        self.__item = None
        self.__chapters_data = None
        self.__chapters = None

        if not query and not url:
            raise ValueError("Expected either query or url.")

        if query:
            self.__load_from_query(query)
        else:
            self.__load_from_url(url)

    def __load_from_query(self, query: str) -> None:
        """Load series data from a search query."""
        resp = niquests.get(SEARCH_API.format(quote(query)))
        data = resp.json()

        items = data.get("items", [])
        if not items:
            raise ValueError(f"No series found for query: {query}")

        self.__item = items[0]

    def __load_from_url(self, url: str) -> None:
        """Load series data from a MangaFire title url."""
        slug_part = url.rstrip("/").split("/title/")[-1]
        hid = slug_part.split("-")[0]

        chapters_url = CHAPTERS_API.format(hid)
        resp = niquests.get(chapters_url)
        chapters_data = resp.json()

        title = chapters_data.get("items", [])
        if not title:
            raise ValueError(f"No chapters found for url: {url}")

        chapter_id = title[0]["id"]
        chapter_resp = niquests.get(CHAPTER_API.format(chapter_id))
        chapter_data = chapter_resp.json().get("data", {})
        title_data = chapter_data.get("title", {})

        if not title_data:
            raise ValueError(f"No title data found for url: {url}")

        self.__item = {
            "id": title_data["id"],
            "hid": title_data["hid"],
            "slug": title_data["slug"],
            "title": title_data["name"],
            "year": None,
            "status": None,
        }

        self.__chapters_data = chapters_data

    def __str__(self) -> str:
        """Return a readable series string."""
        if self.year:
            return f"{self.title} ({self.year})"
        return self.title

    def __repr__(self) -> str:
        """Return a readable debug string."""
        return str(self)

    @property
    def item(self) -> dict:
        """Return the raw series item."""
        return self.__item

    @property
    def id(self) -> int:
        """Return the series id."""
        return self.item["id"]

    @property
    def hid(self) -> str:
        """Return the series hid."""
        return self.item["hid"]

    @property
    def slug(self) -> str:
        """Return the series slug."""
        return self.item["slug"]

    @property
    def title(self) -> str:
        """Return the series title."""
        return self.item["title"]

    @property
    def year(self):
        """Return the series year."""
        return self.item.get("year")

    @property
    def status(self):
        """Return the series status."""
        return self.item.get("status")

    @property
    def url(self) -> str:
        """Return the series url."""
        if self._url:
            return self._url
        return f"https://mangafire.to/title/{self.hid}-{self.slug}"

    @property
    def chapters_api(self) -> str:
        """Return the chapters API url."""
        return CHAPTERS_API.format(self.hid)

    @property
    def chapters_data(self) -> dict:
        """Return raw chapter data."""
        if self.__chapters_data is None:
            resp = niquests.get(self.chapters_api)
            self.__chapters_data = resp.json()
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
                        number=item["number"],
                        name=item["name"],
                        language=item["language"],
                        chapter_type=item["type"],
                        created_at=item["createdAt"],
                    )
                )

        return self.__chapters

    @property
    def official_chapters(self) -> list:
        """Return official chapters."""
        return [chapter for chapter in self.chapters if chapter.type == "official"]

    @property
    def unofficial_chapters(self) -> list:
        """Return unofficial chapters."""
        return [chapter for chapter in self.chapters if chapter.type == "unofficial"]

    @property
    def preferred_chapters(self) -> list:
        """Return official chapters if available, else unofficial chapters."""
        return self.official_chapters or self.unofficial_chapters


if __name__ == "__main__":
    series = MangaFireToSeries(
        url="https://mangafire.to/title/zlwvm-darling-in-the-franxx"
    )

    print(series)
    print()

    print("all chapters:")
    for chapter in series.chapters:
        print("-", chapter)

    print()
    print("official chapters:")
    for chapter in series.official_chapters:
        print("-", chapter)

    print()
    print("unofficial chapters:")
    for chapter in series.unofficial_chapters:
        print("-", chapter)

    print()
    print("preferred chapters:")
    for chapter in series.preferred_chapters:
        print("-", chapter)

    print()
    chapter = series.preferred_chapters[0]
    print("selected chapter:")
    print(chapter)

    print()
    print("images:")
    for image in chapter.images:
        print("-", image.url)

    print()
    image = chapter.images[0]
    print("selected image:")
    print(image.url)
