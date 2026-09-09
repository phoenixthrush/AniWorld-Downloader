from aniworld.models import MangaFireToSeries

url = "https://mangafire.to/title/zlwvm-darling-in-the-franxx"

series = MangaFireToSeries(url)
chapter = series.preferred_chapters[0]  # MangaFireToChapter

print("=== CHAPTER INFO ===")
print("MangaFire Format:", chapter.mangafire_format)
print("Chapter URL:", chapter.chapter_url)
print("Chapter ID:", chapter.chapter_id)
print("Chapter Number:", chapter.chapter_number)
print("Chapter Name:", chapter.chapter_name)
print("Chapter Language:", chapter.chapter_language)
print("Chapter Type:", chapter.chapter_type)
print("Created At:", chapter.created_at)
print("Chapter API URL:", chapter.chapter_api_url)
print("Chapter Data:", chapter.chapter_data)
print("Pages:", chapter.pages)
print("Images:", chapter.images)
print("Folder Name:", chapter.folder_name)
print("Season Number:", chapter.season_number)
print("Episode Number:", chapter.episode_number)
print("Episode Count:", chapter.episode_count)
print("Are Movies:", chapter.are_movies)
print("Title EN:", chapter.title_en)
print("Title DE:", chapter.title_de)
print("Episodes:", chapter.episodes)
print("Selected Path:", chapter.selected_path)
print("Selected Language:", chapter.selected_language)
print("Selected Provider:", chapter.selected_provider)
print("Selected Pages:", chapter.selected_pages)
print("Series:", chapter.series)
print("URL:", chapter.url)

# chapter.download()
