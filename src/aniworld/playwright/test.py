from aniworld.models import SerienstreamEpisode

episode = SerienstreamEpisode(
    "https://serienstream.to/serie/mr-pickles/staffel-1/episode-1"
)

print("=== SERIES INFO ===")
print("URL:", episode.url)
print("Title:", episode.title_de)
print("Redirect URL:", episode.redirect_url)
print("Provider URL:", episode.provider_url)
print("Stream URL:", episode.stream_url)

# Now run this x times until you need to solve a captcha to test the captcha solver
