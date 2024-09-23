# AniWorld Downloader

AniWorld Downloader is a command-line tool designed to download and stream anime content from [aniworld.to](https://aniworld.to). It allows users to fetch single episodes, download seasons, and organize downloads into structured folders. Compatible with Windows, macOS, and Linux, AniWorld Downloader offers a seamless experience across different operating systems.

![PyPI - Downloads](https://img.shields.io/pypi/dm/aniworld?color=blue)
![License](https://img.shields.io/pypi/l/aniworld)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/main/.github/demo.png?raw=true)

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Running with Menu](#running-with-menu)
  - [Command-Line Arguments](#command-line-arguments)
- [Examples](#examples)
  - [Example 1: Download a Single Episode](#example-1-download-a-single-episode)
  - [Example 2: Download multiple episodes](#example-2-download-multiple-episodes)
  - [Example 3: Watch Episodes with Aniskip](#example-3-watch-episodes-with-aniskip)
  - [Example 4: Syncplay with Friends](#example-4-syncplay-with-friends)
  - [Example 5: Download with Specific Provider and Language](#example-5-download-with-specific-provider-and-language)
- [TODO](#todo)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)
- [Support](#support)

---

## Features

- **Download Episodes:** Fetch individual episodes or seasons.
- **Streaming:** Watch episodes directly with integrated players.
- **Netflix Experience:** Automatically play or download the next episode in a series.
- **Multiple Providers:** Support for Vidoza, VOE, Streamtape, and ~~Doodstream~~ (coming soon).
- **Language Options:** Choose between German Dub, English Sub, and German Subtitles.
- **Aniskip Integration:** Automatically skip intros and outros (Unstable yet).
- **Syncplay Support:** Sync playback with friends for a shared viewing experience.
- **Proxy Support:** (Coming Soon) Configure HTTP proxies for your downloads.

---

## Installation

Ensure you have **[Python 3.8](https://www.python.org/downloads/)** or higher installed. Then, install AniWorld Downloader using pip:

```shell
pip install aniworld
```

To update AniWorld Downloader to the latest version:

```shell
pip install -U aniworld
```

To uninstall AniWorld Downloader:

```shell
pip uninstall aniworld -y
```

---

## Usage

### Running with Menu

Launch AniWorld Downloader with an interactive menu:

```shell
aniworld
```

### Command-Line Arguments

AniWorld Downloader provides various command-line options to download and stream anime without using the interactive menu.

## Command-Line Examples

### Example 1: Download a Single Episode

Download episode 1 of "Demon Slayer: Kimetsu no Yaiba":

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

### Example 2: Download multiple episodes

Download multiple episodes of "Demon Slayer":

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-2
```

### Example 3: Watch Episodes with Aniskip

Watch an episode while skipping intros and outros if available:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Watch --aniskip
```

### Example 4: Syncplay with Friends

Syncplay a specific episode with friends:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching
```

If you want to have different languages you can specify it your own and your friends don't have to use the same language as you.

You want to watch it in German Dub you can specify it like this:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "German Dub" --aniskip
```

Your friend wants to watch it in English Sub you can specify it like this:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "English Sub" --aniskip
```

### Example 5: Download with Specific Provider and Language

Download an episode using the VOE provider with English subtitles:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --provider VOE --language "English Sub"
```

### To see all the available options:
```shell
aniworld --help
```

```
options:
  -h, --help            show this help message and exit
  --slug SLUG           Search query - E.g. demon-slayer-kimetsu-no-yaiba
  --link LINK           Search query - E.g.
                        https://aniworld.to/anime/stream/demon-slayer-kimetsu-
                        no-yaiba
  --query QUERY         Search query input - E.g. demon
  --episode EPISODE [EPISODE ...]
                        List of episode URLs - E.g.
                        https://aniworld.to/anime/stream/demon-slayer-kimetsu-
                        no-yaiba/ staffel-1/episode-1,
                        https://aniworld.to/anime/stream/demon-slayer-kimetsu-
                        no-yaiba/ staffel-1/episode-2
  --action {Watch,Download,Syncplay}
                        Action to perform - E.g. Watch, Download, Syncplay
  --output OUTPUT       Download directory (default: ~/Downloads)
  --language {German Dub,English Sub,German Sub}
                        Language choice - E.g. German Dub, English Sub, German
                        Sub
  --provider {Vidoza,Streamtape,VOE,Doodstream}
                        Provider choice - E.g. Vidoza, Streamtape, VOE,
                        Doodstream
  --aniskip             Skip anime opening and ending
  --keep-watching       Continue watching
  --only-direct-link    Output direct link
  --only-command        Output command
  --proxy PROXY         Set HTTP Proxy (not working yet)
  --debug               Enable debug mode
```

---

### Dependencies

AniWorld Downloader relies on the following Python packages:

- `requests`
- `beautifulsoup4`
- `npyscreen`
- `thefuzz`
- `colorlog`
- `py7zr`
- `windows-curses` (only on Windows)

These are automatically installed when you install AniWorld Downloader via pip.

---

## TODO

- [x] Utilize argparse for command-line argument parsing
- [x] Refactor code into modular Python files
- [x] Do not show whole link in selection; display season and episode with name
- [x] Integrate Python logging module
- [x] Add proxy support
- [x] Automatically download and install the following on Windows:
  - [x] mpv
  - [x] yt-dlp
  - [x] Syncplay
- [x] Implement Movies
- [ ] Configure Anime4K installation setup
- [ ] Fix Aniskip Seasons if other than first season
- [ ] Support Doodstream

---

## Credits

- **[mpv](https://github.com/mpv-player/mpv.git)** - Media player used for streaming.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp.git)** - Tool for downloading videos.
- **[Syncplay](https://github.com/Syncplay/syncplay.git)** - Service for synchronized playback with friends.

---

## Contributing

Contributions to AniWorld Downloader are welcome! Whether you're reporting bugs, suggesting features, or submitting pull requests, your input helps improve the project.

---

## License

This project is licensed under the [MIT License](LICENSE).  
See the LICENSE file for more details.

---

## Support

If you need help or have questions about AniWorld Downloader, you can:

- **Report a bug or request a feature** on the [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page.
- **Contact me** directly via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com) or on Matrix at @phoenixthrush:matrix.org.

I appreciate your support and feedback!

If you enjoy using AniWorld Downloader and want to support this project, please consider starring the repository on GitHub. It's free and only takes one click, but it would mean the world to me and motivate me to maintain and improve the project for longer.
