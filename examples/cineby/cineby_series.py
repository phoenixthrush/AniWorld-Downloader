from aniworld.models import CinebySeries

url = "https://www.cineby.at/tv/1396"

series = CinebySeries(url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Media Type:", series.media_type)
print("TMDB ID:", series.tmdb_id)
print("Is Movie:", series.is_movie)
print("Available Language Labels:", series.available_language_labels)
print("Title:", series.title)
print("Title Cleaned:", series.title_cleaned)
print("Release Year:", series.release_year)
print("Poster URL:", series.poster_url)
print("Description:", series.description)
print("Genres:", series.genres)
print("Seasons:", series.seasons)

# series.download()
