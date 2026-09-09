from aniworld.models import KinoxSeries

url = "https://kinox.to/Stream/Avatar-Der_Herr_der_Elemente.html"

series = KinoxSeries(url)
season = series.seasons[0]  # KinoxSeason

print("=== SEASON INFO ===")
print("URL:", season.url)
print("Season Number:", season.season_number)
print("Are Movies:", season.are_movies)
print("Series:", season.series)
print("Episodes:", season.episodes)
print("Episode Count:", season.episode_count)

# season.download()
# season.watch()
# season.syncplay()
