from aniworld.search import fetch_megakino_genres, query_megakino

# Available genre slugs (09/2026 as of right now):
# multfilm (Animation), action, adventure, comedy, crime,
# documentary (Dokumentationen), drama, family, fantasy, history, horror,
# music, mystery, romance, science-fiction (Sci-Fi), tv-movie, thriller,
# war, western.
# Fetch current names and slugs at runtime; comments are only a snapshot.
genres = fetch_megakino_genres()
for genre in genres:
    print(genre["name"], "-", genre["slug"])

# Example 1: First results page for a genre discovered at runtime.
if genres:
    results = query_megakino(genre=genres[0]["slug"])
    for result in results:
        print(result["title"], "-", result["url"])

# Example 2: Horror movies.
results = query_megakino(genre="horror")
for result in results:
    print(result["title"], "-", result["url"])

# Example 3: Animation uses the site's "multfilm" slug.
results = query_megakino(genre="multfilm")
for result in results:
    print(result["title"], "-", result["url"])
