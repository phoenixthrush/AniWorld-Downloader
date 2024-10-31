<a id="readme-top"></a>
# AniWorld Downloader

AniWorld Downloader is a command-line tool built to download and stream anime content from [aniworld.to](https://aniworld.to). With it, you can grab single episodes, download entire seasons, and organize files into neatly structured folders. It’s cross-platform, so it works on Windows, macOS, and Linux for a smooth experience across all major OSes.

![Downloads](https://img.shields.io/pypi/dm/aniworld?label=Downloads&color=blue)
![License](https://img.shields.io/pypi/l/aniworld?label=License&color=blue)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/main/.github/demo.png?raw=true)

<details>
  <summary>Table of Contents</summary>

### Overview
- [Features](#features)
- [TODO](#todo-list)

### Getting Started
- [Installation](#installation)
  - [Latest Release](#installing-aniworld-downloader)
  - [Dev Version (Unstable)](#development-version-unstable)
- [Uninstallation](#uninstallation)

### Usage Guide
- [Usage Basics](#usage)
  - [Running with Menu](#running-with-menu)
  - [Command-Line Arguments](#aniworld-command-options)

### Examples
- [Command-Line Examples](#command-line-examples)
  - [Download a Single Episode](#example-1-download-a-single-episode)
  - [Download Multiple Episodes](#example-2-download-multiple-episodes)
  - [Watch Episodes with Aniskip](#example-3-watch-episodes-with-aniskip)
  - [Syncplay with Friends](#example-4-syncplay-with-friends)
  - [Download with Specific Provider and Language](#example-5-download-with-specific-provider-and-language)
  - [Use Episode File](#example-6-use-an-episode-file)

### Advanced Setup
- [Anime4K Setup](#anime4k-setup)

### FAQs and Support
- [FAQ](#faq)
  - [Providers](#providers)
  - [s.to & bs.to Support](#sto--bsto-support)
- [Support](#support)

### Contribution and Licensing
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

### Project Insights
- [Star History](#star-history)
</details>

## Features

- **Episode Downloads**: Easily download single episodes or entire seasons in one go.
- **Instant Streaming**: Stream episodes directly via the mpv player.
- **Auto Play Next**: Automatically transition to the next episode for uninterrupted viewing.
- **Flexible Providers**: Choose from Vidoza, VOE, and Streamtape, with Doodstream support coming soon.
- **Language Options**: Switch between German Dub, English Sub, or German Sub based on your preference.
- **Aniskip Integration**: Automatically skip intros and outros (currently available for Season 1; expanding soon).
- **Syncplay for Group Watching**: Enjoy synchronized anime watching sessions with friends.
- **Proxy Compatibility**: Set up an HTTP proxy for restricted network environments.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Installation

### Prerequisites

1. **Python Version**: Ensure you have **[Python 3.9](https://www.python.org/downloads/)** or higher installed.  
   - **Note**: Although Python 3.13 is available, it does not include `windows-curses`, which is needed for the menu to work on Windows. To avoid issues, please use **Python 3.12** until `windows-curses` is updated. Check for updates [here](https://pypi.org/project/windows-curses/#files).

### Installing AniWorld Downloader

- To install the latest release of AniWorld Downloader, run:

    ```shell
    pip install aniworld
    ```

- To update to the latest version, use:

    ```shell
    pip install -U aniworld
    ```

### Development Version (Unstable)

- To install the latest development changes directly from GitHub, use:

    ```shell
    pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git#egg=aniworld
    ```

- To update, simply rerun the command above. These builds may be unstable, so it’s good to check regularly.

#### Local Installation (Requires Git)

If you prefer to have the files locally:

1. Clone the repository:

    ```shell
    git clone https://github.com/phoenixthrush/AniWorld-Downloader aniworld
    ```

2. Install it in editable mode:

    ```shell
    pip install -U -e ./aniworld
    ```

3. To keep your local version up to date, run:

    ```shell
    git -C aniworld pull
    ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Uninstallation

To uninstall AniWorld Downloader, run the following command:

```shell
aniworld --uninstall
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

### Running with Menu

To launch AniWorld Downloader with an interactive menu, use:

```shell
aniworld
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Command-Line Examples

AniWorld Downloader supports various command-line options for downloading and streaming anime without using the interactive menu. This allows access to advanced features not available in the menu (e.g., `--aniskip`, `--keep-watching`, `--syncplay-password`).

### Example 1: Download a Single Episode

To download episode 1 of "Demon Slayer: Kimetsu no Yaiba":

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

### Example 2: Download Multiple Episodes

To download multiple episodes of "Demon Slayer":

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-2
```

### Example 3: Watch Episodes with Aniskip

To watch an episode while skipping intros and outros:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Watch --aniskip
```

### Example 4: Syncplay with Friends

To syncplay a specific episode with friends:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching
```

#### Language Options for Syncplay

You can choose different languages for yourself and your friends:

- For German Dub:

    ```shell
    aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "German Dub" --aniskip
    ```

- For English Sub:

    ```shell
    aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "English Sub" --aniskip
    ```

**Note:** Anyone watching the same anime (regardless of episode) will automatically join the room if Syncplay is enabled. To restrict access to strangers, set a password for the room:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching --language "English Sub" --aniskip --syncplay-password beans
```

### Example 5: Download with Specific Provider and Language

To download an episode using the VOE provider with English subtitles:

```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --provider VOE --language "English Sub"
```

### Example 6: Use an Episode File

You can download episodes listed in a text file. Here’s an example of what the text file (`test.txt`) should look like:

```
# The whole anime
https://aniworld.to/anime/stream/alya-sometimes-hides-her-feelings-in-russian

# The whole Season 2
https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-2

# Only Season 3 Episode 13
https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-3/episode-13
```

To download the episodes specified in the file, use:

```shell
aniworld --episode-file /Users/goofball/Downloads/test.txt --language "German Dub"
```

You can also combine this with `Watch` and `Syncplay` actions, along with other arguments as needed.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Anime4K Setup

To set up Anime4K, run the following commands based on your GPU type. This setup will install everything needed to use Anime4K in the mpv player, even outside of AniWorld.

### For Higher-End GPUs
*(e.g., GTX 1080, RTX 2070, RTX 3060, RX 590, Vega 56, 5700XT, 6600XT, M1 Pro, M1 Max, M1 Ultra, M2 Pro, M2 Max)*

```shell
aniworld --anime4k High
```

### For Lower-End GPUs
*(e.g., GTX 980, GTX 1060, RX 570, M1, M2, Intel chips)*

```shell
aniworld --anime4k Low
```

### To Remove Anime4K
If you want to uninstall Anime4K, use the following command:

```shell
aniworld --anime4k Remove
```

### Notes
- This installation saves all necessary files into the **mpv** directory.
- You can switch between settings by specifying the optimized modes (`High` or `Low`).
- Use the `Remove` option to uninstall Anime4K easily.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## AniWorld Command Options

```shell
aniworld --help
```

```
usage: aniworld [-h] [--slug SLUG] [--link LINK] [--query QUERY]
                [--episode EPISODE [EPISODE ...]] [--episode-file EPISODE_FILE]
                [--action {Watch,Download,Syncplay}] [--output OUTPUT]
                [--output-directory OUTPUT_DIRECTORY]
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
  --output OUTPUT       Download directory E.g. /Users/phoenixthrush/Downloads
  --output-directory OUTPUT_DIRECTORY
                        Final download directory E.g ExampleDirectory, defaults to anime
                        name if not specified
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
  --uninstall           Self uninstall
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Dependencies

AniWorld Downloader requires the following Python packages:

- `requests`
- `beautifulsoup4`
- `npyscreen`
- `thefuzz`
- `colorlog`
- `py7zr`
- `packaging`
- `yt-dlp`
- `windows-curses` (only for Windows users)

These packages are automatically installed when you set up AniWorld Downloader using pip.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## TODO List

### Completed Tasks
- **Command-Line Improvements**
  - [x] Implement `argparse` for command-line argument parsing.
  - [x] Refactor the code into modular Python files.
  - [x] Display season and episode names instead of full links in selections.

- **Logging and Proxy Support**
  - [x] Integrate the Python logging module.
  - [x] Add support for proxy configurations.

- **Automatic Installations**
  - [x] Automatically download and install the following on Windows & Linux:
    - [x] `mpv`
    - [x] `yt-dlp`
    - [x] `Syncplay`

- **Feature Enhancements**
  - [x] Implement movie support.
  - [x] Configure Anime4K installation for:
    - [x] Windows
    - [x] MacOS
    - [x] Linux
  - [x] Add options for Syncplay room passwords.
  - [x] Add mass file support.
  - [x] Add Captcha bypass for headless browser fetches.
  - [x] Allow changing final output folder
  
- **Bug Fixes**
  - [x] Fix season episode count.
  - [x] Fix yt-dlp progress bar on Windows.
  - [x] Fix empty output for unavailable selected languages.
  - [x] Use anime title instead of slug on the episode list.
  - [x] Add time to cancel.
  - [x] Fix output folder for mass processed files.
  - [x] Fix Syncplay and mpv video desync issue (use Vidoza for Watch & Syncplay).
  - [x] Automatically clean up old logs.
  - [x] Separate the functionalities of aniskip and auto start & exit.

### Upcoming Tasks
- [-] Sanitise echo strings on Windows
- [ ] Fix is_tail_running on MacOS
- [ ] Implement an ordered list for provider fallback in globals.py.
- [ ] Remove unnecessary dependencies, add additional installation variants (e.g., without curses dependency).
- [ ] Fix Aniskip for seasons beyond the first.
- [ ] Optimize performance to reduce requests and eliminate duplicate function calls.
- [ ] Add support for Doodstream.
- [ ] Anonymize logs by removing usernames

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## FAQ

### Providers
Aniworld-Downloader currently supports three providers:
- **VOE**
- **Vidoza**
- **Streamtape**

**Doodstream** is not supported due to constant backend updates that block download attempts. While I initially had support for it, Doodstream's backend changes rendered my previous method obsolete.

#### Download and Viewing Recommendations
In older versions, the default provider for both downloading and watching with syncplay and mpv was Vidoza. However, since Vidoza and Streamtape throttle download speeds, I recommend using **VOE** for downloads, as it can fully utilize your bandwidth.

**Drawback of VOE:**
- Many fragments can be invalid, affecting playback with mpv. While downloads using yt-dlp work fine, invalid fragments may cause scenes to skip or glitch, leading to noticeable disruptions, especially during syncplay, where different fragment issues among viewers can result in annoying jumps.

**Current Recommendations:**
- **Download in this order:**  
  VOE > Vidoza > Streamtape

- **For viewing in mpv or syncplay:**  
  Vidoza > Streamtape > VOE

### s.to & bs.to Support
I previously had support for s.to in a separate branch, but it is now unmaintained and untested. Currently, I do not plan to re-implement support for s.to, as I've focused on stabilizing the existing code. Before adding new providers, I need to streamline the backend, which is somewhat messy due to redundant functions and fetches from recent feature additions.

**Note on Adding s.to Support:**
- Adding s.to support would not be difficult—it only requires one fewer fetch than Aniworld's current method to access streaming providers. If anyone is interested in contributing to this effort, I would be happy to merge the addition.

There are already other tools that support s.to. For terminal-based viewing of s.to, check out my friend's project called **gucken**—he’s doing great work there. 

Regarding Aniworld’s claim of hosting 1,000+ license-free anime, it’s worth noting that they also stream new shows that may require subscriptions elsewhere. Supporting s.to could mean indirectly accessing copyrighted content, such as Netflix originals. As I do not host any content but fetch it directly from streaming providers, I am not liable for any issues arising from downloading anime.

Feel free to contribute! Any help is appreciated, and I’d be happy to merge in support for s.to or bs.to if it gets added.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Credits
- **[mpv](https://github.com/mpv-player/mpv.git)**: Media player used for streaming.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp.git)**: Tool for downloading videos.
- **[Syncplay](https://github.com/Syncplay/syncplay.git)**: Service for synchronized playback with friends.
- **[Anime4K](https://github.com/bloc97/Anime4K)**: A high-quality real-time upscaler for anime video.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing
Contributions to AniWorld Downloader are welcome! Your input helps improve the project, whether it’s through:
- Reporting bugs
- Suggesting features
- Submitting pull requests

### Contributors
- **Lulu** (since Sep 14, 2024)  
  ![wakatime](https://wakatime.com/badge/user/ebc8f6ad-7a1c-4f3a-ad43-cc402feab5fc/project/408bbea7-23d0-4d6c-846d-79628e6b136c.svg)

- **Tmaster055** (since Oct 21, 2024)  
  ![wakatime](https://wakatime.com/badge/user/79a1926c-65a1-4f1c-baf3-368712ebbf97/project/5f191c34-1ee2-4850-95c3-8d85d516c449.svg)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License
This project is licensed under the **[MIT License](LICENSE)**.  
For more details, see the LICENSE file.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Support

I’ve received several reports from users experiencing unexpected menu quits. Recently, streaming providers have started blocking IP addresses from downloading. You can bypass this by using a VPN. You might try using the `--use-playwright` option instead, though it's still experimental and may not be very effective. Additionally, run the following command with the `--debug` flag in a separate terminal:

```shell
# Windows PowerShell (opens automatically in newer versions)
Get-Content -Wait $env:TEMP\aniworld.log 

# Linux
tail -f /tmp/aniworld.log 

# MacOS (opens automatically in newer versions)
tail -f $TMPDIR/aniworld.log 
```

This will typically reveal a timeout error, indicating the domain couldn’t be reached or another issue.

### How to Get Help
If you still need assistance with AniWorld Downloader, you can:

- **File a report** via the [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page.
- **Contact me directly** via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com), on Matrix `@phoenixthrush:matrix.org`, or on Discord `phoenixthrush`.

While I do respond to emails, opening a GitHub issue is preferable, even for installation questions, so others can find solutions too. However, I’m still happy to help via email if you prefer.

If you enjoy AniWorld Downloader and want to support the project, please consider starring the repository on GitHub. It’s a small gesture that means a lot and motivates me to keep improving the project.

Thank you for your support and feedback!

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=phoenixthrush/Aniworld-Downloader&type=Date)](https://star-history.com/#phoenixthrush/Aniworld-Downloader&Date)

<p align="right">(<a href="#readme-top">back to top</a>)</p>
