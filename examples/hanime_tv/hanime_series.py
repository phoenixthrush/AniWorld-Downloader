from aniworld.models import HanimeTVSeries

url = "https://hanime.tv/videos/hentai/reika-wa-karei-na-boku-no-joou-4"

series = HanimeTVSeries(url)

print("=== SERIES INFO ===")
print("URL:", series.url)
print("Title:", series.title)
print("Description:", series.description)
print("Genres:", series.genres)
print("Release Year:", series.release_year)
print("Poster URL:", series.poster_url)
print("Episode Slugs:", series.episode_slugs)
print("Season Count:", series.season_count)

# series.download()
# series.watch()
# series.syncplay()
