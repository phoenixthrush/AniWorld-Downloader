from aniworld.models import SerienstreamEpisode

url = "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1"

# ----------------------------
# Language variations
# ----------------------------
variations = [
    ("German Dub", "VOE"),  # German audio, no subtitles
    ("English Dub", "VOE"),  # English audio, no subtitles
]

print("Downloading all available variations into a single MKV file...")

for language, provider in variations:
    print(f"Downloading: {language} via {provider}")

    episode = SerienstreamEpisode(
        url=url, selected_language=language, selected_provider=provider
    )

    # Download will mux everything into one MKV file
    episode.download()

print("Done!")
