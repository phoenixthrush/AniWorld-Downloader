# AniWorld Downloader

AniWorld Downloader is a command-line tool designed to download and stream anime content from [aniworld.to](https://aniworld.to). It allows users to fetch single episodes, download seasons, and organize downloads into structured folders. Compatible with Windows, macOS, and Linux, AniWorld Downloader offers a seamless experience across different operating systems.

![PyPI - Downloads](https://img.shields.io/pypi/dm/aniworld?color=blue)
![License](https://img.shields.io/pypi/l/aniworld)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/main/.github/demo.png?raw=true)

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Latest Release](#latest-release)
  - [Dev Version](#dev-version-unstable)
- [Uninstallation](#uninstallation)
- [Usage](#usage)
  - [Running with Menu](#running-with-menu)
  - [Command-Line Arguments](#command-line-arguments)
- [Examples](#command-line-examples)
  - [Example 1: Download a Single Episode](#example-1-download-a-single-episode)
  - [Example 2: Download multiple episodes](#example-2-download-multiple-episodes)
  - [Example 3: Watch Episodes with Aniskip](#example-3-watch-episodes-with-aniskip)
  - [Example 4: Syncplay with Friends](#example-4-syncplay-with-friends)
  - [Example 5: Download with Specific Provider and Language](#example-5-download-with-specific-provider-and-language)
- [Anime4K Setup](#anime4k-setup-currently-windows-only)
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
- **Proxy Support:** Configure HTTP proxies for your downloads.

---

## Installation

### Latest Release

Ensure you have **[Python 3.8](https://www.python.org/downloads/)** or higher installed. Then, install AniWorld Downloader using pip:

```shell
pip install aniworld
```

To update AniWorld Downloader to the latest version:

```shell
pip install -U aniworld
```

### Dev Version (unstable)

To install the latest development changes on GitHub (assuming you have Git installed):

```shell
git clone https://github.com/phoenixthrush/AniWorld-Downloader aniworld
pip install -U -e ./aniworld
```

Please keep it to the latest version by doing this regularly:

```shell
git -C aniworld pull
```

---

## Uninstallation

To uninstall AniWorld Downloader:

```shell
pip uninstall -y aniworld
```

To also delete all leftover files, run the following command:

On Windows:
```batch
del "%APPDATA%\mpv\scripts\autoexit.lua" >nul 2>&1
del "%APPDATA%\mpv\scripts\autostart.lua" >nul 2>&1
del "%APPDATA%\mpv\scripts\skip.lua" >nul 2>&1

del "%APPDATA%\mpv\input.conf" >nul 2>&1
del "%APPDATA%\mpv\mpv.conf" >nul 2>&1
rmdir /s /q "%APPDATA%\mpv\shaders" >nul 2>&1

rmdir /s /q "%APPDATA%\aniworld" >nul 2>&1
```

On MacOS & Linux:
```shell
rm -f $HOME/.config/mpv/scripts/autoexit.lua
rm -f $HOME/.config/mpv/scripts/autostart.lua
rm -f $HOME/.config/mpv/scripts/skip.lua
```

---

## Usage

### Running with Menu

Launch AniWorld Downloader with an interactive menu:

```shell
aniworld
```

### Command-Line Arguments

AniWorld Downloader provides various command-line options to download and stream anime without using the interactive menu. This also allows users to utilize advanced options that can't be selected through the normal menu, such as (--aniskip, --keep-watching, --syncplay-password, ...).

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

Please note that anyone watching the same anime (regardless of the episode) will automatically join the room if Syncplay is enabled. If you prefer to restrict access to strangers, you can set a password for the room that both parties must specify to join.

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "English Sub" --aniskip --syncplay-password beans
```

### Example 5: Download with Specific Provider and Language

Download an episode using the VOE provider with English subtitles:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --provider VOE --language "English Sub"
```

---

## Anime4K Setup

To install Anime4K persistently, use the following commands once:

### For Higher-End GPU
(Eg. GTX 980, GTX 1060, RX 570)
```shell
aniworld --anime4k High
```

### For Lower-End GPU
(Eg. GTX 1080, RTX 2070, RTX 3060, RX 590, Vega 56, 5700XT, 6600XT)

```shell
aniworld --anime4k Low
```

### To Remove Anime4K
```shell
aniworld --anime4k Remove
```

This installs all necessary files into the mpv directory, enabling Anime4K in mpv even outside of AniWorld. You can switch between settings by specifying the different optimized modes. To remove it, simply use the remove option.

---

### To see all the available options:
```shell
aniworld --help
```

```
usage: aniworld [-h] [--slug SLUG] [--link LINK] [--query QUERY]
                [--episode EPISODE [EPISODE ...]] [--action {Watch,Download,Syncplay}]
                [--output OUTPUT] [--language {German Dub,English Sub,German Sub}]
                [--provider {Vidoza,Streamtape,VOE,Doodstream}] [--aniskip]
                [--keep-watching] [--anime4k {High,Low,Remove}]
                [--syncplay-password SYNCPLAY_PASSWORD [SYNCPLAY_PASSWORD ...]]
                [--only-direct-link] [--only-command] [--proxy PROXY] [--debug]

Parse optional command line arguments.

options:
  -h, --help            show this help message and exit
  --slug SLUG           Search query - E.g. demon-slayer-kimetsu-no-yaiba
  --link LINK           Search query - E.g. https://aniworld.to/anime/stream/demon-
                        slayer-kimetsu-no-yaiba
  --query QUERY         Search query input - E.g. demon
  --episode EPISODE [EPISODE ...]
                        List of episode URLs
  --action {Watch,Download,Syncplay}
                        Action to perform
  --output OUTPUT       Download directory
  --language {German Dub,English Sub,German Sub}
                        Language choice
  --provider {Vidoza,Streamtape,VOE,Doodstream}
                        Provider choice
  --aniskip             Skip intro and outro
  --keep-watching       Continue watching
  --anime4k {High,Low,Remove}
                        Set Anime4K optimised mode (High Eg.: GTX 1080, RTX 2070, RTX
                        3060, RX 590, Vega 56, 5700XT, 6600XT; Low Eg.: GTX 980, GTX
                        1060, RX 570, or Remove). This only needs to be run once to set
                        or remove as the changes are persistent.
  --syncplay-password SYNCPLAY_PASSWORD [SYNCPLAY_PASSWORD ...]
                        Set a syncplay room password
  --only-direct-link    Output direct link
  --only-command        Output command
  --proxy PROXY         Set HTTP Proxy - E.g. http://0.0.0.0:8080
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

- [x] Add argparse for command-line argument parsing.
- [x] Refactor the code into modular Python files.
- [x] Avoid displaying the full link in selections; instead, show the season and episode names.
- [x] Add Python logging module.
- [x] Add support for proxy configurations.
- [x] Automatically download and install the following on Windows:
  - [x] mpv
  - [x] yt-dlp
  - [x] Syncplay
- [x] Implement movie support.
- [x] Configure the Anime4K installation setup:
  - [x] Windows
  - [x] MacOS
  - [x] Linux
- [x] Fix season episode count.
- [x] Add an option for Syncplay room passwords.
- [ ] Fix yt-dlp progress bar on Windows 
- [ ] Fix empty output when the selected language is unavailable.
- [ ] Use anime title instead of slug on episode list
- [ ] Optimize performance: less requests and no duplicate function calls
- [ ] Fix Aniskip for seasons other than the first.
- [ ] Support Doodstream.

---

## Credits

- **[mpv](https://github.com/mpv-player/mpv.git)** - Media player used for streaming.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp.git)** - Tool for downloading videos.
- **[Syncplay](https://github.com/Syncplay/syncplay.git)** - Service for synchronized playback with friends.
- **[Anime4K](https://github.com/bloc97/Anime4K)** - A high-quality real-time upscaler for anime video.

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
