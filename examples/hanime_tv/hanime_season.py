from aniworld.models import HanimeTVSeries

url = "https://hanime.tv/videos/hentai/reika-wa-karei-na-boku-no-joou-4"

series = HanimeTVSeries(url)
season = series.seasons[0]  # HanimeTVSeason

print("=== SEASON INFO ===")
print("URL:", season.url)
print("Series:", season.series)
print("Season Number:", season.season_number)
print("Are Movies:", season.are_movies)
print("Episode Count:", season.episode_count)
print("Episodes:", season.episodes)

# season.download()
# season.watch()
# season.syncplay()
