from aniworld.models import CinebySeries

url = "https://www.cineby.at/tv/1396"

series = CinebySeries(url)
season = series.seasons[0]  # CinebySeason

print("=== SEASON INFO ===")
print("URL:", season.url)
print("TMDB ID:", season.tmdb_id)
print("Are Movies:", season.are_movies)
print("Season Number:", season.season_number)
print("Series:", season.series)
print("Episodes:", season.episodes)
print("Episode Count:", season.episode_count)
print("Language Labels:", season.language_labels)

# season.download()
# season.watch()
# season.syncplay()
