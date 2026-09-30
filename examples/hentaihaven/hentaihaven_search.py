from aniworld.search import query_hentaihaven

# Every result URL can be downloaded with: aniworld <url>
for result in query_hentaihaven("Ane wa Yanmama", limit=10):
    print(result["title"], "-", result["url"])
