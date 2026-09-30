from aniworld.models import HentaiHavenSeries

series = HentaiHavenSeries("https://hentaihaven.xxx/watch/ane-wa-yanmama-junyuu-chuu/")
for episode in series.episodes:
    print(episode.episode_number, episode.title, episode.url)

series.download()
