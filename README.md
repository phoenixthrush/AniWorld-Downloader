# AniWorld Downloader

AniWorld Downloader is a command-line tool designed to download and stream anime content from [aniworld.to](https://aniworld.to). It allows users to fetch single episodes, download seasons, and organize downloads into structured folders. Compatible with Windows, macOS, and Linux, AniWorld Downloader offers a seamless experience across different operating systems.

![Downloads](https://img.shields.io/pypi/dm/aniworld?label=Downloads&color=blue)
![License](https://img.shields.io/pypi/l/aniworld?label=License&color=blue)

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
  - [Example 6: Use Episode File](#example-6-use-episode-file)
- [Anime4K Setup](#anime4k-setup)
- [TODO](#todo)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)
- [Support](#support)
- [Star History](#star-history)

---

## Features

- **Episode Download:** Grab individual episodes or full seasons of anime.
- **Streaming Capability:** Stream episodes directly using the mpv player.
- **Seamless Viewing:** Automatically move to the next episode for continuous watching.
- **Provider Support:** Use providers like Vidoza, VOE, Streamtape, with Doodstream support coming soon.
- **Language Selection:** Choose between German Dub, English Sub, or German Subtitles.
- **Aniskip Functionality:** Automatically skip intros and outros (currently only works for first seasons; support for later seasons is on the todo).
- **Syncplay Integration:** Watch anime with friends in sync, perfect for shared viewing.
- **Proxy Configuration:** Set up a HTTP proxy if needed.

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

To install the latest development changes on GitHub:

```shell
pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git#egg=aniworld
```

To update, simply rerun the command above. It's recommended to do this regularly as these builds are often unstable.

Or if you want the files locally (assuming you have Git installed):

```shell
git clone https://github.com/phoenixthrush/AniWorld-Downloader aniworld
pip install -U -e ./aniworld
```

If you have the files locally using the second option above, you need to keep it updated by doing this regularly:

```shell
git -C aniworld pull
```

---

## Uninstallation

To uninstall AniWorld Downloader:

```shell
aniworld --uninstall
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

### Example 6: Use Episode File

test.txt
```
# The whole anime
https://aniworld.to/anime/stream/alya-sometimes-hides-her-feelings-in-russian

# The whole Season 2
https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-2

# Only Season 3 Episode 13
https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-3/episode-13
```

```shell
aniworld --episode-file /Users/goofball/Downloads/test.txt --language "German Dub"
```

You can also use the `Watch` and `Syncplay` actions along with other arguments as normal.

---

## Anime4K Setup

To install Anime4K persistently, use the following commands once:

### For Higher-End GPU
(Eg. GTX 1080, RTX 2070, RTX 3060, RX 590, Vega 56, 5700XT, 6600XT, M1 Pro, M1 Max, M1 Ultra, M2 Pro, M2 Max)

```shell
aniworld --anime4k High
```

### For Lower-End GPU
(Eg. GTX 980, GTX 1060, RX 570, M1, M2, Intel chips)

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
                [--episode EPISODE [EPISODE ...]] [--episode-file EPISODE_FILE]
                [--action {Watch,Download,Syncplay}] [--output OUTPUT]
                [--language {German Dub,English Sub,German Sub}]
                [--provider {Vidoza,Streamtape,VOE,Doodstream}] [--aniskip]
                [--keep-watching] [--anime4k {High,Low,Remove}]
                [--syncplay-password SYNCPLAY_PASSWORD [SYNCPLAY_PASSWORD ...]]
                [--only-direct-link] [--only-command] [--proxy PROXY] [--use-playwright]
                [--debug] [--version] [--update {mpv,yt-dlp,syncplay,all}] [--uninstall]

Parse optional command line arguments.

options:
  -h, --help            show this help message and exit
  --slug SLUG           Search query - E.g. demon-slayer-kimetsu-no-yaiba
  --link LINK           Search query - E.g. https://aniworld.to/anime/stream/demon-
                        slayer-kimetsu-no-yaiba
  --query QUERY         Search query input - E.g. demon
  --episode EPISODE [EPISODE ...]
                        List of episode URLs
  --episode-file EPISODE_FILE
                        File path containing a list of episode URLs
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
  --use-playwright      Bypass fetching with a headless browser using Playwright instead
                        (EXPERIMENTAL!!!)
  --debug               Enable debug mode
  --version             Print version info
  --update {mpv,yt-dlp,syncplay,all}
                        Update mpv, yt-dlp, syncplay, or all.
  --uninstall           Self uninstalls
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
- `packaging`
- `yt-dlp`
- `windows-curses` (only on Windows)

These are automatically installed when you install AniWorld Downloader via pip.

---

## TODO

- [x] Add argparse for command-line argument parsing.
- [x] Refactor the code into modular Python files.
- [x] Avoid displaying the full link in selections; instead, show the season and episode names.
- [x] Add Python logging module.
- [x] Add support for proxy configurations.
- [x] Automatically download and install the following on Windows & Linux:
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
- [x] Add mass file support.
- [x] Fix yt-dlp progress bar on Windows.
- [x] Fix empty output when the selected language is unavailable.
- [x] Use anime title instead of slug on episode list.
- [x] Add time to cancel.
- [x] Fix mass processed files output folder.
- [x] Fix Syncplay & mpv video desync issue. (-> use Vidoza for Watch & Syncplay)
- [ ] Add Captcha Bypass/ Headless Browser fetches.
- [ ] Fix Aniskip for seasons other than the first.
- [ ] Optimize performance: less requests and no duplicate function calls.
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

Lulu (since Sep 14, 2024)<br>
![wakatime](https://wakatime.com/badge/user/ebc8f6ad-7a1c-4f3a-ad43-cc402feab5fc/project/408bbea7-23d0-4d6c-846d-79628e6b136c.svg)

Tmaster055 (since Oct 21, 2024)<br>
![wakatime](https://wakatime.com/badge/user/79a1926c-65a1-4f1c-baf3-368712ebbf97/project/5f191c34-1ee2-4850-95c3-8d85d516c449.svg)

---

## License

This project is licensed under the [MIT License](LICENSE).  
See the LICENSE file for more details.

---

## Support

I've received several emails from users reporting that the menu unexpectedly quits without any explanation. In the past few days, streaming providers have started blocking IP addresses from downloading. You can bypass this by using a VPN. If you're still facing issues, try running the following command with the --debug flag in a separate terminal:

```shell
Get-Content -Wait $env:TEMP\aniworld.log # Windows PowerShell
tail -f /tmp/aniworld.log # Linux
tail -f $TMPDIR/aniworld.log # MacOS
```

This will usually show a timeout error, indicating that the domain couldn't be reached or something else went wrong. I will be working on a workaround to this that uses a different url fetch method that will work with fetching the urls using playwright or an alternative that will open a headless browser and optionally handle javascript if needed.

If you still need assistance with AniWorld Downloader, you can:

- **Receive help** via [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page.
- **Reach out to me** directly via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com), on Matrix `@phoenixthrush:matrix.org` or on Discord `phoenixthrush`.

Also, while I do respond to emails, opening a GitHub issue would be great, even for installation questions. That way, others with the same problem can find solutions. But don't worry—I’ll still help you via email if you prefer that.

If you enjoy AniWorld Downloader and want to support the project, please consider starring the repository on GitHub. It’s a small gesture, but it means a lot and motivates me to keep improving the project.

I appreciate your support and feedback!

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=phoenixthrush/Aniworld-Downloader&type=Date)](https://star-history.com/#phoenixthrush/Aniworld-Downloader&Date)
