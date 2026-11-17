from aniworld.models import AniworldSeries

url = "https://aniworld.to/anime/stream/highschool-dxd"

series = AniworldSeries(url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Title:", series.title)
print("Title Clean:", series.title_cleaned)
print("Description:", series.description)
print("Genres:", series.genres)
print("Release year:", series.release_year)
print("Poster URL:", series.poster_url)
print("IMDB ID:", series.imdb)
print("MAL ID:", series.mal_id)
print("Has movies:", series.has_movies)
print("Seasons:", series.seasons)
print("Season count:", series.season_count)
print()

# series.download()
# series.watch()
# series.syncplay()
