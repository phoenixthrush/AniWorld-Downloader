from aniworld.models import CinebySeries

url = "https://www.cineby.at/tv/1396"

series = CinebySeries(url)
season = series.seasons[0]
episode = season.episodes[0]  # CinebyEpisode

print("=== EPISODE INFO ===")
print("URL:", episode.url)
print("Media Type:", episode.media_type)
print("TMDB ID:", episode.tmdb_id)
print("Is Movie:", episode.is_movie)
print("Title:", episode.title)
print("Title Cleaned:", episode.title_cleaned)
print("Release Year:", episode.release_year)
print("Title DE:", episode.title_de)
print("Title EN:", episode.title_en)
print("Episode Number:", episode.episode_number)
print("Season Number:", episode.season_number)
print("Series:", episode.series)
print("Season:", episode.season)
print("Selected Path:", episode.selected_path)
print("Selected Language:", episode.selected_language)
print("Available Language Labels:", episode.available_language_labels)
print("Selected Provider:", episode.selected_provider)
print("Provider Data:", episode.provider_data)
print("Base Folder:", episode._base_folder)
print("Folder Path:", episode._folder_path)
print("File Name:", episode._file_name)
print("File Extension:", episode._file_extension)
print("Episode Path:", episode._episode_path)
print("Is Downloaded:", episode.is_downloaded)
print("Stream URL:", episode.stream_url)

# episode.download()
# episode.watch()
# episode.syncplay()
