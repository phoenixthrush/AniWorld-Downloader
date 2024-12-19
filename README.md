<a id="readme-top"></a>
# AniWorld Downloader

AniWorld Downloader is a command-line tool for downloading and streaming anime, series and movies, compatible with Windows, macOS, and Linux.

![Downloads](https://img.shields.io/pypi/dm/aniworld?label=Downloads&color=blue)
![License](https://img.shields.io/pypi/l/aniworld?label=License&color=blue)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/next/.github/assets/demo.png?raw=true)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Installation (Requires Git)

- To install the latest version from GitHub, run:

```shell
pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git@next#egg=aniworld
```

To update, simply rerun the above command. Note that these builds may be unstable, so regular checks are recommended.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Usage

AniWorld Downloader can be utilized in three different ways: through an interactive menu, via command-line arguments, or as a Python library.

#### Menu Example
To start the interactive menu, simply run:
```shell
aniworld
```

#### Command-Line Arguments Example
To download a specific episode directly, use:
```shell
aniworld --episode https://aniworld.to/anime/stream/loner-life-in-another-world/staffel-1/episode-1
```

#### Library Example
You can also use AniWorld Downloader as a library in your Python scripts:
```python
from aniworld.models import Anime, Episode

# Create an Anime object with a list of Episode objects
anime = Anime(
    episode_list=[
        Episode(
            slug="food-wars-shokugeki-no-sma",
            season=1,
            episode=5
        ),
        Episode(
            link="https://aniworld.to/anime/stream/food-wars-shokugeki-no-sma/staffel-1/episode-6"
        )
    ]
)

# Iterate over episodes and print Episode objects
for episode in anime:
    print(episode)
    print(episode.get_direct_link("VOE", "German Sub"))
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Roadmap

- [ ] Resolve issues with subprocess commands in Watch, Download, and Syncplay features
- [ ] Correct the issue of anime titles being `None`, which may resolve the `get_mal_id_from_title` crash
- [ ] Implement automatic fetching for mpv and syncplay
- [ ] Integrate support for Anime4K
- [ ] Introduce options for syncplay rooms
- [ ] Enable support for episode files
- [ ] Enhance performance by filling unnecessary variables only when they are used at runtime, rather than directly in classes
- [ ] Implement proxy support
- [ ] Add support for Playwright

<details>
  <summary>Command-Line Arguments</summary>

- [x] --help
- [ ] --version
- [ ] --debug
- [ ] --uninstall
- [ ] --update
- [ ] --slug
- [ ] --link
- [ ] --query
- [x] --episode
- [ ] --episode-file
- [ ] --episode-local
- [ ] --action
- [ ] --output
- [ ] --output-directory
- [ ] --language
- [ ] --provider
- [ ] --anime4k
- [ ] --syncplay-hostname
- [ ] --syncplay-username
- [ ] --syncplay-room
- [ ] --syncplay-password
- [ ] --aniskip
- [ ] --keep-watching
- [ ] --random-anime
- [ ] --only-direct-link
- [ ] --only-command
- [ ] --proxy
- [ ] --use-playwright

</details>

<p align="right">(<a href="#readme-top">back to top</a>)</p>