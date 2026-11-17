from aniworld.models import MegaKinoEpisode

test_url = "https://megakino8.com/films/205-deadpool.html"
movie = MegaKinoEpisode(test_url)

print("Title:", movie.title)
print("Cleaned Title:", movie.title_cleaned)
print("Description:", movie.description)
print("Genres:", movie.genres)
print("Release Year:", movie.release_year)
print("Poster URL:", movie.poster_url)
print("Player Sources:", movie.player_sources)

# movie.download()
