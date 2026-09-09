from aniworld.models import HanimeTVEpisode

url = "https://hanime.tv/videos/hentai/reika-wa-karei-na-boku-no-joou-4"

episode = HanimeTVEpisode(url)

print("=== EPISODE INFO ===")
print("URL:", episode.url)
print("Title EN:", episode.title_en)
print("Title DE:", episode.title_de)
print("Episode Number:", episode.episode_number)
print("Series:", episode.series)
print("Season:", episode.season)
print("Description:", episode.description)
print("Poster URL:", episode.poster_url)
print("Provider Data:", episode.provider_data)
print("Selected Path:", episode.selected_path)
print("Selected Language:", episode.selected_language)
print("Selected Provider:", episode.selected_provider)
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
