from aniworld.models import BurningSeriesSeries

url = "https://bs.to/serie/Breaking-Bad"

series = BurningSeriesSeries(url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Slug:", series.slug)
print("Title:", series.title)
print("Title Cleaned:", series.title_cleaned)
print("Release Year:", series.release_year)
print("Description:", series.description)
print("Genres:", series.genres)
print("Poster URL:", series.poster_url)
print("Seasons:", series.seasons)

# series.download()
