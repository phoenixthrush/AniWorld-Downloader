from aniworld.search import query_burningseries

# Available genres (09/2026 as of right now; names are case-insensitive):
# Abenteuer, Action, Animation, Anime, Anime-China, Anime-Ecchi, Anime-Horror, Anime-
# Isekai, Anime-Mecha, Anime-Musik, Anime-Romance, Anime-Slice of Life, Anime-Sport,
# Anime-Super-Power, Anime-Supernatural, Comedy, Dokumentation, Dokusoap, Drama,
# Dramedy, Familie, Fantasy, Game, History, Horror, Jugend, K-Drama, Kinderserie,
# Krankenhaus, Krieg, Krimi, Magic, Märchen, Mystery, Reality-TV, Romantik, Science-
# Fiction, Sitcom, Sport, Telenovela, Thriller, Western, Zeichentrick.

# Example 1: All horror series.
results = query_burningseries(genre="Horror")
print("Horror:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

# Example 2: Keyword within a genre.
results = query_burningseries("star", genre="Science-Fiction")
print("Science-Fiction matching 'star':", len(results))
for result in results:
    print(result["title"], "-", result["url"])

# Example 3: Genre names also accept lowercase.
results = query_burningseries(genre="krimi")
print("Krimi:", len(results))
for result in results:
    print(result["title"], "-", result["url"])
