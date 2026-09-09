from aniworld.models import MangaFireToSeries

url = "https://mangafire.to/title/zlwvm-darling-in-the-franxx"

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

# series.download()
