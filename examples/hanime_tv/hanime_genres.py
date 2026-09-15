from aniworld.extractors.provider.hanime_tv import fetch_hanime_genres, search_hanime

# Available genre tags (09/2026 as of right now):
# 2000-year-old dragon girl, 3d, ahegao, anal, bdsm, big boobs, blow job, bondage, boob
# job, censored, comedy, cosplay, creampie, dark skin, facial, fantasy, filmed, foot
# job, futanari, gangbang, glasses, hand job, harem, hd, horror, incest, inflation,
# lactation, maid, masturbation, milf, mind break, mind control, monster, nekomimi,
# ntr, nurse, orgy, plot, pov, pregnant, public sex, rimjob, scat, school girl,
# softcore, swimsuit, teacher, tentacle, threesome, toys, trap, tsundere, ugly bastard,
# uncensored, vanilla, virgin, watersports, x-ray, yaoi, yuri.
# Fetch the current list at runtime; the comments above are only a snapshot.
genres = fetch_hanime_genres()
print("Available genres:", len(genres))
for genre in genres:
    print(genre)

# Sort options (09/2026):
# None / "": Recent Upload (default)
# created_at_asc: Oldest Upload
# released_at_desc / released_at_asc: Newest / Oldest Release
# views_desc / views_asc: Most / Least Views
# likes_desc: Most Likes
# name_asc / name_desc: Alphabetical A-Z / Z-A

# Fetch up to 24 results from a genre's first page.
results = search_hanime(genre="fantasy")
print("Fantasy results:", len(results))
for result in results:
    print(result["name"], "-", "https://hanime.tv/videos/hentai/" + result["slug"])

# Fetch all cards on the first page without a result limit.
results = search_hanime(genre="comedy", limit=None, sort="views_desc")
print("Comedy results, most views:", len(results))
for result in results:
    print(result["name"], "-", "https://hanime.tv/videos/hentai/" + result["slug"])
