from aniworld.search import query_kinox

# limit caps the result count; None keeps the site's existing scope, 0 skips fetching.
# Available genre slugs (09/2026 as of right now):
# Action, Adult, Adventure, Animation, Anime, Biography, Bollywood, Comedy,
# Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Musical,
# Mystery, Reality-TV, Romance, Sci-Fi, Short, Sport, Thriller, War, Western.
# Each call fetches the genre's Top 100 at runtime, preserving the site's ranking.

results = query_kinox(limit=10, genre="Action")
print("Action Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

results = query_kinox(limit=10, genre="Horror")
print("Horror Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

results = query_kinox(limit=10, genre="Sci-Fi")
print("Sci-Fi Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])
