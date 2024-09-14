# AniWorld Downloader

AniWorld Downloader is a command-line tool designed to download and stream anime content from [aniworld.to](https://aniworld.to). It allows users to fetch single episodes, download entire seasons, and organize downloads into structured folders. Compatible with Windows, macOS, and Linux, AniWorld Downloader offers a seamless experience across different operating systems.

![PyPI - Downloads](https://img.shields.io/pypi/dm/aniworld?color=blue)
![License](https://img.shields.io/pypi/l/aniworld)

![AniWorld Downloader - Demo](https://raw.githubusercontent.com/phoenixthrush/AniWorld-Downloader/development/.github/demo.jpg)

## Table of Contents

- [Description](#description)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Running with Menu](#running-with-menu)
  - [Command-Line Arguments](#command-line-arguments)
    - [Download a Single Episode](#download-a-single-episode)
    - [Download All Seasons](#download-all-seasons)
    - [Watch with Automatic Continuation](#watch-with-automatic-continuation)
    - [Using Specific Providers and Languages](#using-specific-providers-and-languages)
- [Examples](#examples)
- [Requirements](#requirements)
- [TODO](#todo)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)
- [Support](#support)

## Features

- **Download Episodes:** Fetch individual episodes or entire seasons.
- **Streaming:** Watch episodes directly with integrated players.
- **Netflix Experience:** Automatically play or download the next episode in a series.
- **Multiple Providers:** Support for Vidoza, VOE, Streamtape and ~~Doodstream~~ (coming soon).
- **Language Options:** Choose between German Dub, English Sub, and German Subtitles.
- **Aniskip Integration:** Automatically skip intros and outros.
- **Syncplay Support:** Sync playback with friends for a shared viewing experience.
- **Proxy Support:** (Coming Soon) Configure HTTP proxies for your downloads.

## Installation

Ensure you have **Python 3.8** or higher installed. Then, install AniWorld Downloader using pip:

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

## Usage

### Running with Menu

Launch AniWorld Downloader with an interactive menu:

```shell
aniworld
```

### Command-Line Arguments

AniWorld Downloader provides various command-line options to customize your experience without using the interactive menu.

#### Download a Single Episode

Download a specific episode by providing its URL:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

#### Download All Seasons

Automatically download or watch all episodes across all seasons:

```shell
aniworld --query "demon-slayer-kimetsu-no-yaiba" --all-seasons
```

#### Watch with Automatic Continuation

Play an episode and automatically continue to the next one:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --keep-watching
```

#### Using Specific Providers and Languages

Specify the streaming provider and language option:

```shell
aniworld --query "food wars" --provider "VOE" --language "English Sub"
```

## Examples

### Example 1: Download a Single Episode

Download episode 1 of "Demon Slayer: Kimetsu no Yaiba":

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

### Example 2: Download an Entire Season

Download all episodes from season 1 of "Demon Slayer":

```shell
aniworld --query "demon-slayer-kimetsu-no-yaiba" --keep-watching
```

### Example 3: Watch Episodes with Aniskip

Watch an episode while skipping intros and outros:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --aniskip --action Watch
```

### Example 4: Syncplay with Friends

Syncplay a specific episode with friends:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay
```

### Example 5: Download with Specific Provider and Language

Download an episode using the VOE provider with English subtitles:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --provider "VOE" --language "English Sub"
```

## Requirements

- **[Python 3.8](https://www.python.org/downloads/)** or higher

### Dependencies

AniWorld Downloader relies on the following Python packages:

- `requests`
- `beautifulsoup4`
- `npyscreen`
- `thefuzz`
- `windows-curses` (only on Windows)

These are automatically installed when you install AniWorld Downloader via pip.

## TODO

- [x] Utilize argparse for command-line argument parsing
- [x] Refactor code into modular Python files
- [x] Do not show whole link in selection; display season and episode with name
- [ ] Add proxy support
- [ ] Fix Aniskip finding wrong timestamps
- [ ] Fix wrong episode count on keep-watching per season
- [ ] Configure Anime4K installation setup
- [ ] Fix Aniskip finding wrong MAL ID
- [ ] Integrate Python logging module
- [ ] Support Doodstream

## Contributing

Contributions to AniWorld Downloader are welcome! Whether you're reporting bugs, suggesting features, or submitting pull requests, your input helps improve the project.

## Credits

- **[mpv](https://github.com/mpv-player/mpv.git)** - Media player used for streaming.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp.git)** - Tool for downloading videos.
- **[Syncplay](https://github.com/Syncplay/syncplay.git)** - Service for synchronized playback with friends.

## License

This project is licensed under the [MIT License](LICENSE).  
See the LICENSE file for more details.

---

Thank you for using AniWorld Downloader! If you encounter any issues or have suggestions, feel free to reach out through the [issue tracker](https://github.com/phoenixthrush/AniWorld-Downloader/issues).

## Support

If you need help or have questions about AniWorld Downloader, you can:

- **Report a bug or request a feature** on the [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page.
- **Contact me** directly via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com) or on Matrix at @phoenixthrush:matrix.org.

I appreciate your support and feedback!
