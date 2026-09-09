from aniworld.models import KinoxSeries

url = "https://kinox.to/Stream/Avatar-Der_Herr_der_Elemente.html"

series = KinoxSeries(url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Slug:", series.slug)
print("Title:", series.title)
print("Title Cleaned:", series.title_cleaned)
print("Release Year:", series.release_year)
print("Poster URL:", series.poster_url)
print("Description:", series.description)
print("Genres:", series.genres)
print("Language Labels:", series.language_labels)
print("Is Movie:", series.is_movie)
print("Seasons:", series.seasons)

# series.download()
