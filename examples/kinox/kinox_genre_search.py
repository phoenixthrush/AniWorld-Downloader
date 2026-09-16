from aniworld.search import query_kinox

# Available genre slugs (09/2026 as of right now):
# Action, Adult, Adventure, Animation, Anime, Biography, Bollywood, Comedy,
# Crime, Documentary, Drama, Family, Fantasy, History, Horror, Music, Musical,
# Mystery, Reality-TV, Romance, Sci-Fi, Short, Sport, Thriller, War, Western.
# Each call fetches the genre's Top 100 at runtime, preserving the site's ranking.

results = query_kinox(genre="Action")
print("Action Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

results = query_kinox(genre="Horror")
print("Horror Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

results = query_kinox(genre="Sci-Fi")
print("Sci-Fi Top 100:", len(results))
for result in results:
    print(result["title"], "-", result["url"])
