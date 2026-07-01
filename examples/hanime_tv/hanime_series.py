from aniworld.models import HanimeTVSeries

url = "https://hanime.tv/videos/hentai/reika-wa-karei-na-boku-no-joou-4"

series = HanimeTVSeries(url)

print("=== SERIES INFO ===")
print(series.to_dict())

# series.download()
# series.watch()
# series.syncplay()
