from aniworld.models import BurningSeriesSeries

url = "https://bs.to/serie/Breaking-Bad"

series = BurningSeriesSeries(url)
season = series.seasons[0]  # BurningSeriesSeason

print("=== SEASON INFO ===")
print("URL:", season.url)
print("Season Number:", season.season_number)
print("Are Movies:", season.are_movies)
print("Series:", season.series)
print("Episodes:", season.episodes)
print("Episode Count:", season.episode_count)
print("Language Labels:", season.language_labels)

# season.download()
# season.watch()
# season.syncplay()
