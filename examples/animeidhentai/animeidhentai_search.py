from aniworld.search import query_animeidhentai

# Every result URL can be downloaded with: aniworld <url>
for result in query_animeidhentai("Inaka ni wa Kore kurai", limit=10):
    print(result["title"], "-", result["url"])
