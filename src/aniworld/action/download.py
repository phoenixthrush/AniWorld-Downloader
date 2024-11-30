from aniworld.models import Anime


def download(anime: Anime):
    for episode in anime:
        output_file = f"{anime.title} S{episode.season}E{episode.episode}"
        command = [
            "yt-dlp",
            "--fragment-retries", "infinite",
            "--concurrent-fragments", "4",
            "-o", output_file,
            "--quiet",
            "--no-warnings",
            "this-is-direct-link",
            "--progress"
        ]
        #if episode.provider == "Vidmoly":
           #command.insert(9, '--add-header Referer: "https://vidmoly.to"')

        print(command)
