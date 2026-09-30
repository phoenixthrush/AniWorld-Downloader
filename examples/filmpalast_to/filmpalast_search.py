from aniworld.search import fetch_filmpalast_genres, query_filmpalast

# limit caps the result count; None keeps the site's existing scope, 0 skips fetching.
# Available genres (09/2026 as of right now):
# Abenteuer, Action, Animation, Biographie, Dokumentation, Drama, Englisch,
# Familie, Fantasy, Geschichte, Horror, Komödie, Krieg, Krimi, Musik,
# Mystery, Romantik, Sci-Fi, Sport, Thriller, Western, Zeichentrick.
# Fetch current names and slugs at runtime; comments are only a snapshot.
genres = fetch_filmpalast_genres()
for genre in genres:
    print(genre["name"], "-", genre["slug"])

# Example 1: The first results page for a genre discovered at runtime.
if genres:
    results = query_filmpalast(limit=10, genre=genres[0]["slug"])
    for result in results:
        print(result["title"], "-", result["url"])

# Example 2: Horror movies.
results = query_filmpalast(limit=10, genre="Horror")
for result in results:
    print(result["title"], "-", result["url"])

# Example 3: Genre slugs with umlauts are URL-encoded automatically.
results = query_filmpalast(limit=10, genre="Komödie")
for result in results:
    print(result["title"], "-", result["url"])
