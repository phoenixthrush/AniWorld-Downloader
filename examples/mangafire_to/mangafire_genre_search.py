from urllib.parse import urljoin

from aniworld.models.mangafire_to.series import fetch_mangafire_genres, search_series

# Available genres (09/2026 as of right now; fetched at runtime, not an allowlist):
# Action, Adult, Adventure, Avant Garde, Boys Love, Comedy, Crime, Demons, Drama,
# Ecchi, Fantasy, Girls Love, Gourmet, Hentai, Historical, Horror, Isekai, Iyashikei,
# Josei, Kids, Magic, Magical Girls, Mahou Shoujo, Martial Arts, Mature, Mecha,
# Medical, Military, Music, Mystery, Parody, Philosophical, Psychological, Romance,
# School, Sci-Fi, Seinen, Shoujo, Shounen, Slice of Life, Smut, Space, Sports, Super
# Power, Superhero, Supernatural, Suspense, Thriller, Tragedy, Vampire, Wuxia.
# Sort options (09/2026):
# relevance:desc, chapter_updated_at:desc, created_at:desc, title:asc, title:desc,
# year:desc, year:asc, score:desc, trending:desc, views_7d:desc, views_30d:desc,
# views_total:desc, follows_total:desc.
# limit caps results; None follows all pages, 0 skips fetching.
genres = fetch_mangafire_genres()
for genre in genres:
    print(genre["name"], "-", genre["id"])

# Example 1: Genre name, highest rated first.
results = search_series(genre="Action", sort="score:desc", limit=10)
for result in results:
    print(result["title"], "-", urljoin("https://mangafire.to", result["url"]))

# Example 2: Keyword within a genre.
results = search_series("dragon", genre="Fantasy", limit=10)
for result in results:
    print(result["title"], "-", urljoin("https://mangafire.to", result["url"]))

# Example 3: Use an ID discovered at runtime, alphabetically.
if genres:
    results = search_series(genre=genres[0]["id"], sort="title:asc", limit=10)
    for result in results:
        print(result["title"], "-", urljoin("https://mangafire.to", result["url"]))
