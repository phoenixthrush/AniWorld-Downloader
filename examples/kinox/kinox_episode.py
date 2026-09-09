from aniworld.models import KinoxSeries

url = "https://kinox.to/Stream/Avatar-Der_Herr_der_Elemente.html"

series = KinoxSeries(url)
season = series.seasons[0]
episode = season.episodes[0]  # KinoxEpisode

print("=== EPISODE INFO ===")
print("URL:", episode.url)
print("Is Movie:", episode.is_movie)
print("Series:", episode.series)
print("Season:", episode.season)
print("Episode Number:", episode.episode_number)
print("Season Number:", episode.season_number)
print("Title DE:", episode.title_de)
print("Title EN:", episode.title_en)
print("Selected Path:", episode.selected_path)
print("Selected Language:", episode.selected_language)
print("Selected Provider:", episode.selected_provider)
print("Provider Data:", episode.provider_data)
print("Base Folder:", episode._base_folder)
print("Folder Path:", episode._folder_path)
print("File Name:", episode._file_name)
print("File Extension:", episode._file_extension)
print("Episode Path:", episode._episode_path)
print("Is Downloaded:", episode.is_downloaded)
print("Redirect URL:", episode.redirect_url)
print("Provider URL:", episode.provider_url)
print("Stream URL:", episode.stream_url)

# episode.download()
# episode.watch()
# episode.syncplay()
