from aniworld.config import INVERSE_LANG_KEY_MAP, LANG_LABELS, Audio, Subtitles
from aniworld.models import AniworldEpisode

# episode_url = "https://aniworld.to/anime/stream/highschool-dxd/staffel-1/episode-1"
episode_url = "https://aniworld.to/anime/stream/needless/staffel-1/episode-7"

episode = AniworldEpisode(episode_url)

if episode.provider_link(episode.selected_language, episode.selected_provider) is None:
    first_available_language = next(iter(episode.provider_data._data))
    episode.selected_language = LANG_LABELS[
        INVERSE_LANG_KEY_MAP[first_available_language]
    ]

print("=== EPISODE INFO ===")
print("URL:", episode.url)
print("Title DE:", episode.title_de)
print("Title EN:", episode.title_en)
print("Episode Number:", episode.episode_number)
print("Provider Data:", episode.provider_data)
print("Selected Path:", episode.selected_path)
print("Selected Language:", episode.selected_language)
print("Selected Provider:", episode.selected_provider)
print("Redirect URL:", episode.redirect_url)
print("Provider URL:", episode.provider_url)
print("Stream URL:", episode.stream_url)
print("Base Folder:", episode._base_folder)
print("Folder Path:", episode._folder_path)
print("File Name:", episode._file_name)
print("File Extension:", episode._file_extension)
print("Episode Path:", episode._episode_path)
print("Is Movie:", episode.is_movie)
print("Is Downloaded:", episode.is_downloaded)
print("Skip Times:", episode.skip_times)
print()

print("=== SERIES INFO ===")
print("Title:", episode.series.title)
print()

print("=== SEASON INFO ===")
print("Season URL:", episode.season.url)
print()

print("=== CUSTOM PROVIDER LINK ===")
language = (Audio.JAPANESE, Subtitles.GERMAN)
provider = "Doodstream"

provider_link = episode.provider_link(language=language, provider=provider)
print("Provider Link:", provider_link)

episode.selected_language = LANG_LABELS[INVERSE_LANG_KEY_MAP[language]]
episode.selected_provider = provider

print("Download Language:", episode.selected_language)
print("Download Provider:", episode.selected_provider)

episode.download()
# episode.watch()
# episode.syncplay()
