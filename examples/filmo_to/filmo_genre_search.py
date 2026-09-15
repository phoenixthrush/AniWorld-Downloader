from aniworld.search import query_filmo

# Genre IDs (09/2026 as of right now):
# 1 Action, 2 Adventure, 3 Animation, 4 Comedy, 5 Crime, 6 Documentary,
# 7 Drama, 8 Family, 9 Fantasy, 10 History, 11 Horror, 12 Music, 13 Mystery,
# 14 Romance, 15 Science Fiction, 16 TV Movie, 17 Thriller, 18 War, 19 Western.
# All filters are optional; omit them or use None / "".
# Sort: title_asc, title_desc, release_desc, release_asc, rating_desc, rating_asc.
# Country codes (09/2026): US, GB, DE, FR, IT, ES, JP, KR, CN, IN, CA, AU,
# MX, BR, SE, NO, DK, FI, PL, NL, BE, AT, CH, IE, NZ, PT, GR, CZ, HU, RO,
# TR, UA, AR, CL, CO, IL, ZA, TH, VN, PH, ID, MY, TW, HK, SG, AE, EG, RU.

# Example 1: Horror movies, newest releases first.
results = query_filmo(genre_id=11, sort="release_desc")
print("Horror:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

# Example 2: Science fiction from 2020, between 90 and 120 minutes.
results = query_filmo(genre_id=15, year=2020, runtime_min=90, runtime_max=120)
print("Science fiction, 2020, 90-120 minutes:", len(results))
for result in results:
    print(result["title"], "-", result["url"])

# Example 3: German movies, highest ratings first, without a genre filter.
results = query_filmo(country="DE", sort="rating_desc")
print("German movies, by rating:", len(results))
for result in results:
    print(result["title"], "-", result["url"])
