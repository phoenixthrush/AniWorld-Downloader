from aniworld.search import query_hentai_tv

# Every result URL can be downloaded with: aniworld <url>
for result in query_hentai_tv("Hamehara", limit=10):
    print(result["title"], "-", result["url"])
