from aniworld.search import query_s_to

# limit caps the result count; None keeps the site's existing scope, 0 skips fetching.
# Available genres (09/2026 as of right now):
# abenteuer, action, animation, anime, comedy, dokumentation, dokusoap,
# drama, dramedy, familie, fantasy, history, horror, jugend, kinderserie,
# krankenhaus, krimi, mystery, romantik, science-fiction, sitcom, telenovela,
# thriller, western, zeichentrick, k-drama, reality-tv, true-crime.
# FSK, production years, and sort are optional; omit them or use None / "".
# Sort: name_asc, name_desc, latest, release, ratings_desc.

# Example 1: Genre only, using the site's default sorting.
results = query_s_to(limit=10, genre="horror")
print("Horror:", len(results))
for result in results:
    print(result["title"], "-", "https://serienstream.to" + result["link"])

# Example 2: FSK 18, sorted by rating, without production year limits.
results = query_s_to(limit=10, genre="horror", fsk=18, sort="ratings_desc")
print("Horror, FSK 18, by rating:", len(results))
for result in results:
    print(result["title"], "-", "https://serienstream.to" + result["link"])

# Example 3: Production year range, alphabetically, without an FSK filter.
results = query_s_to(
    limit=10,
    genre="science-fiction",
    prod_start=2000,
    prod_end=2026,
    sort="name_asc",
)
print("Science fiction, 2000-2026, alphabetical:", len(results))
for result in results:
    print(result["title"], "-", "https://serienstream.to" + result["link"])
