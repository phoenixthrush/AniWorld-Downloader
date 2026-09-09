from aniworld.models import MangaFireToSeries

url = "https://mangafire.to/title/zlwvm-darling-in-the-franxx"

series = MangaFireToSeries(url)
chapter = series.preferred_chapters[0]
page = chapter.pages[0]  # MangaFireToPage

print("=== PAGE INFO ===")
print("Chapter:", page.chapter)
print("Page Number:", page.page_number)
print("Image:", page.image)
print("Image URL:", page.image_url)
print("File Name:", page.file_name)

print("=== IMAGE INFO ===")
print("Image URL:", page.image.image_url)
print("Image Width:", page.image.width)
print("Image Height:", page.image.height)
print("Image File Suffix:", page.image.file_suffix)

# page.download()
