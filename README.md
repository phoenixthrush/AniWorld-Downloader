<a id="readme-top"></a>
# AniWorld Downloader

AniWorld Downloader is a command-line tool for downloading and streaming anime, series and movies, compatible with Windows, macOS, and Linux.

![Downloads](https://img.shields.io/pypi/dm/aniworld?label=Downloads&color=blue)
![License](https://img.shields.io/pypi/l/aniworld?label=License&color=blue)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/next/.github/assets/demo.png?raw=true)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Features

- **Episode Downloads**: Easily download single episodes or entire seasons in one go.
- **Instant Streaming**: Stream episodes directly via the mpv player.
- **Auto Play Next**: Automatically transition to the next episode for uninterrupted viewing.
- **Flexible Providers**: Choose from Vidoza, VOE, and Streamtape, with Doodstream support coming soon.
- **Language Options**: Switch between German Dub, English Sub, or German Sub based on your preference.
- **Aniskip Integration**: Automatically skip intros and outros.
- **Syncplay for Group Watching**: Enjoy synchronized anime watching sessions with friends.

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

## Dependencies

AniWorld Downloader requires the following Python packages:

- `requests`
- `beautifulsoup4`
- `npyscreen`
- `yt-dlp`
- `windows-curses` (only for Windows users)

These packages are automatically installed when you set up AniWorld Downloader using pip.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Credits
- **[mpv](https://github.com/mpv-player/mpv.git)**: Media player used for streaming.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp.git)**: Tool for downloading videos.
- **[Syncplay](https://github.com/Syncplay/syncplay.git)**: Service for synchronized playback with friends.
- **[Anime4K](https://github.com/bloc97/Anime4K)**: A high-quality real-time upscaler for anime video.
- **[htv](https://github.com/rxqv/htv)**: Backend implementation for hanime playback and downloading.
- **[logo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/next/src/aniworld/icon.png?raw=true)**: The binary logo used at `src/aniworld/icon.webp`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Still Left Todo

- [ ] Generate episodes on --episode argument with only anime or season as in episode file
- [ ] Enable support for episode files
- [ ] Implement provider fallback list
- [ ] Integrate support for Anime4K
- [ ] Introduce options for syncplay rooms

<details>
  <summary>Command-Line Arguments</summary>

- [x] --help
- [x] --version
- [x] --debug
- [ ] --uninstall
- [x] --update
- [ ] --slug
- [ ] --link
- [ ] --query
- [x] --episode
- [ ] --episode-file
- [x] --episode-local
- [ ] --action
- [ ] --output
- [x] --output-directory
- [x] --language
- [x] --provider
- [ ] --anime4k
- [x] --syncplay-hostname
- [x] --syncplay-username
- [x] --syncplay-room
- [x] --syncplay-password
- [x] --aniskip
- [ ] --keep-watching
- [ ] --random-anime
- [x] --only-direct-link
- [x] --only-command

</details>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing
Contributions to AniWorld Downloader are welcome! Your input helps improve the project, whether it’s through:
- Reporting bugs
- Suggesting features
- Submitting pull requests

### Contributors

<a href="https://github.com/phoenixthrush/Aniworld-Downloader/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=phoenixthrush/Aniworld-Downloader" />
</a>

- **Lulu** (since Sep 14, 2024)  
  ![wakatime](https://wakatime.com/badge/user/ebc8f6ad-7a1c-4f3a-ad43-cc402feab5fc/project/408bbea7-23d0-4d6c-846d-79628e6b136c.svg)

- **Tmaster055** (since Oct 21, 2024)  
  ![wakatime](https://wakatime.com/badge/user/79a1926c-65a1-4f1c-baf3-368712ebbf97/project/5f191c34-1ee2-4850-95c3-8d85d516c449.svg)

  Thank you [Tmaster055](https://github.com/Tmaster055) for fixing Aniskip by fetching the correct MAL ID!<br>
  Thank you [fundyjo](https://github.com/fundyjo) for the Doodstream extractor!

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Support

I’ve received several reports from users experiencing unexpected menu quits. Recently, streaming providers have started blocking IP addresses from downloading. You can bypass this by using a VPN.

### How to Get Help
If you still need assistance with AniWorld Downloader, you can:

- **File a report** via the [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page.
- **Contact me directly** via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com), on Matrix `@phoenixthrush:matrix.org`, or on Discord `phoenixthrush`.

While I do respond to emails, opening a GitHub issue is preferable, even for installation questions, so others can find solutions too. However, I’m still happy to help via email if you prefer.

If you enjoy AniWorld Downloader and want to support the project, please consider starring the repository on GitHub. It’s a small gesture that means a lot and motivates me to keep improving the project.

Thank you for your support and feedback!

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Legal Disclaimer

Aniworld-Downloader is intended only for accessing publicly available content and does not support or encourage piracy or copyright infringement. As the program's creator, I am not liable for, nor associated with, any external links or the content they lead to.

All content accessed through this program is freely available online, and the program does not host or distribute copyrighted material. The program has no control over the nature, content, or availability of the linked websites.

If you have concerns or objections about the content accessed via this program, please address them to the relevant website owners, administrators, or hosting providers. Thank you.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=phoenixthrush/Aniworld-Downloader&type=Date)](https://star-history.com/#phoenixthrush/Aniworld-Downloader&Date)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License
This project is licensed under the **[MIT License](LICENSE)**.  
For more details, see the LICENSE file.