from aniworld.models import MangaFireToSeries

url = "https://mangafire.to/title/z9w-velvet-kisss"

series = MangaFireToSeries(url)

print("=== SERIES INFO ===")
print("Series URL:", series.series_url)
print("Series Item:", series.series_item)
print("Hid:", series.hid)
print("Slug:", series.slug)
print("Title:", series.title)
print("Title Cleaned:", series.title_cleaned)
print("Poster URL:", series.poster_url)
print("Description:", series.description)
print("Genres:", series.genres)
print("Release Year:", series.release_year)
print("Chapters API URL:", series.chapters_api_url)
print("Chapters Data:", series.chapters_data)
print("Chapters:", series.chapters)
print("Seasons:", series.seasons)
print("Official Chapters:", series.official_chapters)
print("Unofficial Chapters:", series.unofficial_chapters)
print("Preferred Chapters:", series.preferred_chapters)

print("Available Volumes:", series.volumes)
print("Archive Units:", series.download_items("epub"))

# To save archives, install: python -m pip install "aniworld[epub]"
# series.download(format="epub")  # Or format="cbz" without the extra.
# Archives use source volumes when available, otherwise preferred chapters.
# Velvet Kiss currently has no published volume grouping on MangaFire.
# series.download(format="jpg")  # Loose images remain organized by chapter.
