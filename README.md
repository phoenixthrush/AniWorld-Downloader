<a id="readme-top"></a>

# AniWorld Downloader v4

AniWorld Downloader is a cross-platform tool for streaming and downloading anime from aniworld.to, as well as series from s.to, with support for more sites being added over time. It runs on Windows, macOS, and Linux, providing a seamless experience for offline viewing or instant playback.

![GitHub Release](https://img.shields.io/github/v/release/phoenixthrush/AniWorld-Downloader)
[![PyPI Downloads](https://static.pepy.tech/badge/aniworld)](https://pepy.tech/projects/aniworld)
![PyPI - Downloads](https://img.shields.io/pypi/dm/aniworld)
![GitHub License](https://img.shields.io/github/license/phoenixthrush/AniWorld-Downloader)
![GitHub Issues or Pull Requests](https://img.shields.io/github/issues/phoenixthrush/AniWorld-Downloader)
[![PayPal Donate](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://www.paypal.com/paypalme/justnekochan)
![GitHub Repo stars](https://img.shields.io/github/stars/phoenixthrush/AniWorld-Downloader)
![GitHub forks](https://img.shields.io/github/forks/phoenixthrush/AniWorld-Downloader)

Menu | WebUI (AniWorld) | WebUI (SerienStream)
:-------------------------:|:-------------------------:|:-------------------------:
![Menu Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/demo.png?raw=true) | ![AniWorld Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/demo-aniworld.png?raw=true) | ![SerienStream Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/demo-serienstream.png?raw=true)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## TL;DR - Quick Start

```bash
# Install stable release (needs Python installed)
pip install -U aniworld

# Or install latest GitHub commit (needs Git installed)
pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git@models#egg=aniworld

# Launch AniWorld Downloader using Web UI
aniworld -w

# Using Menu
aniworld
```

> **Tip**: Use the stable release for general use. The GitHub version includes the latest features and fixes but may be less stable.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Documentation

For full user guides, tutorials, and troubleshooting, visit the [official documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Still in Development

This project is actively being improved. Current work in progress includes:

- [ ] fix episode download cleanup on KeyboardInterrupt in menu
- [ ] add support for aniskip feature on IINA
- [ ] Split Web UI SSO dependencies into separate `extras` section
- [ ] Implement `keep-watching` argument for continuous playback
- [ ] Fix Nuitka build crash: use Python 3.12 (non-MSVC builds unsupported on newer versions)
- [ ] Remove empty lines below actions when running `docker run -it`

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Features

- **Downloading** – Grab full series, individual seasons, or single episodes for offline viewing
- **Streaming** – Watch episodes instantly using **mpv**, **IINA**, or **Syncplay**
- **Auto-Next Playback** – Seamlessly move to the next episode without interruption
- **Multiple Providers** – Stream from various sources on **aniworld.to** and **s.to**
- **Language Preferences** – Switch between **German Dub**, **English Sub**, or **German Sub**
- **Muxing** – Automatically combine video and audio streams into a single file
- **AniSkip Integration** – Skip intros and outros on AniWorld for a smoother experience
- **Group Watching** – Sync anime and series sessions with friends via **Syncplay**
- **Web Interface** – Browse, download, and manage your queue with a modern web UI
- **Docker Ready** – Deploy easily using **Docker** or **Docker Compose**

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Supported Providers

| Provider | Status | Last Tested |
| --- | --- | --- |
| VOE | ✅ Working | 06/26 |
| Vidoza | ✅ Working | 02/26 |
| Vidmoly | ✅ Working | 02/26 |
| Filemoon | ❌ Broken | 02/26 |
| Doodstream | ❌ Broken | 02/26 |
| Hanime | ⏳ Not Implemented | — |
| LoadX | ⏳ Not Implemented | — |
| Luluvdo | ⏳ Not Implemented | — |
| Streamtape | ⏳ Not Implemented | — |

### Currently Prioritized Providers

- **AniWorld** – VOE, Filemoon, Vidmoly
- **SerienStream** – VOE, Vidoza

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Docker

Build the AniWorld Downloader Docker image:

```bash
docker build -t aniworld .
```

### Running the Container

- **macOS / Linux (bash/zsh):**

```bash
docker run -it --rm \
  -v "${PWD}/Downloads:/app/Downloads" \
  aniworld python -m aniworld
```

- **Windows (PowerShell):**

```powershell
docker run -it --rm `
  -v "${PWD}\Downloads:/app/Downloads" `
  aniworld python -m aniworld
```

- **Windows (CMD):**

```cmd
docker run -it --rm ^
  -v "%cd%\Downloads:/app/Downloads" ^
  aniworld python -m aniworld
```

> **Note:**
> Mount your local `Downloads` folder to `/app/Downloads` in the container to save downloaded episodes. You can adjust the host path as needed.

### Docker Compose (with Web UI)

Start AniWorld Downloader using Docker Compose:

```bash
docker-compose up -d --build
```

This command will:

- **Build the Docker image** if it hasn’t been built yet
- **Start the container** in detached mode (`-d`)
- Enable the **Web UI** for easier interaction
- Automatically **restart the container unless stopped manually** (`restart: unless-stopped`)

To stop the container:

```bash
docker-compose down
```

> **Tip:** Ensure your `docker-compose.yml` correctly configures volumes and ports if you want to persist downloads or access the Web UI externally.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Contributions to AniWorld Downloader are **highly appreciated**! You can help improve the project in several ways:

- **Report Bugs** – Identify and report issues to improve functionality
- **Suggest Features** – Share ideas to expand the tool's capabilities
- **Submit Pull Requests** – Contribute code to fix bugs or add new features
- **Improve Documentation** – Help enhance user guides, tutorials, and technical documentation

Before submitting contributions, please check the repository for existing issues or feature requests to avoid duplicates.

### Contributors

<a href="https://github.com/phoenixthrush/AniWorld-Downloader/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=phoenixthrush/AniWorld-Downloader" alt="Contributors" />
</a>

- **Lulu** (since Sep 14, 2024)  
  [![wakatime](https://wakatime.com/badge/user/ebc8f6ad-7a1c-4f3a-ad43-cc402feab5fc/project/f39b2952-8865-4176-8ccc-4716e73d0df3.svg)](https://wakatime.com/badge/user/ebc8f6ad-7a1c-4f3a-ad43-cc402feab5fc/project/f39b2952-8865-4176-8ccc-4716e73d0df3)

- **Tmaster055** (since Oct 21, 2024)  
  [![Wakatime Badge](https://wakatime.com/badge/user/79a1926c-65a1-4f1c-baf3-368712ebbf97/project/5f191c34-1ee2-4850-95c3-8d85d516c449.svg)](https://wakatime.com/badge/user/79a1926c-65a1-4f1c-baf3-368712ebbf97/project/5f191c34-1ee2-4850-95c3-8d85d516c449.svg)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Dependencies

AniWorld Downloader uses a small set of Python packages for networking, terminal UI, media handling, web features, authentication, and configuration.

### Core dependencies

- **niquests** – HTTP requests
- **npyscreen** – Text-based terminal UI
- **ffmpeg-python** – Python bindings for FFmpeg (requires FFmpeg installed on your system)
- **python-dotenv** – Loads environment variables from a `.env` file
- **rich** – Styled terminal output
- **fake-useragent** – Generates user-agent strings
- **packaging** – Version parsing and comparison
- **cryptography** – Cryptographic utilities
- **patchright** – Browser automation support for captcha handling

### Web / server dependencies

- **requests** – Standard HTTP library
- **flask** – Web framework
- **flask-wtf** – Forms and CSRF protection for Flask
- **authlib** – OAuth and authentication helpers
- **waitress** – Production WSGI server

### Platform-specific dependencies

- **windows-curses** – Enables curses support for `npyscreen` on Windows (installed only on Windows and only for Python versions below 3.14)

All dependencies are installed automatically when AniWorld Downloader is installed with `pip`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Credits

AniWorld Downloader builds upon the work of several outstanding open-source projects:

- **[mpv](https://github.com/mpv-player/mpv.git)** – A versatile media player used for seamless video streaming
- **[IINA](https://github.com/iina/iina.git)** – Modern macOS media player built on mpv, offering a sleek interface and advanced playback features
- **[Syncplay](https://github.com/Syncplay/syncplay.git)** – Enables synchronized playback sessions with friends
- **[Anime4K](https://github.com/bloc97/Anime4K)** – Real-time upscaler for enhancing anime video quality
- **[Aniskip](https://api.aniskip.com/api-docs)** – Provides opening and ending skip times for the Aniskip extension
- **[flag-icons](https://github.com/lipis/flag-icons)** – Collection of SVG country flags

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Other Cool Projects

- **[Jellyfin AniWorld Downloader](https://github.com/SiroxCW/Jellyfin-AniWorld-Downloader)** by **[SiroxCW](https://github.com/SiroxCW)** – A Jellyfin plugin that lets you browse and download anime & series directly from AniWorld, fully integrated into your media server.

- **[AniBridge](https://github.com/Zzackllack/AniBridge)** by **[Zzackllack](https://github.com/Zzackllack)** – A minimal FastAPI service that bridges anime and series streaming catalogues (AniWorld, SerienStream/s.to, MegaKino) with automation tools.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Support

If you need help with AniWorld Downloader, you have several options:

- **Submit an issue** on the [GitHub Issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) page – preferred for installation problems, bug reports, or feature requests, as it helps others benefit from shared solutions
- **Contact directly** via email at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com) **or on our Discord server**. [Join here](https://discord.gg/BfDvrKd8V5)

While email support is available, opening a GitHub issue is encouraged whenever possible.

If you find AniWorld Downloader useful, please star the repository on GitHub. Your support is greatly appreciated and motivates continued development.

Thank you for using AniWorld Downloader!

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Legal Disclaimer

AniWorld Downloader is a **client-side** tool that enables access to content hosted on third-party websites. It **does not host, upload, store, or distribute any media itself**.

This software is **not intended to promote piracy or copyright infringement**. You are solely responsible for how you use AniWorld Downloader and for ensuring that your use **complies with applicable laws** and the **terms of service of the websites you access**.

The developer provides this project **"as is"** and is **not responsible for**:

- Third-party content
- External links
- The availability, accuracy, legality, or reliability of any third-party service

If you have concerns about specific content, **contact the relevant website owner, administrator, or hosting provider**.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=phoenixthrush/AniWorld-Downloader&type=Date)](https://star-history.com/#phoenixthrush/AniWorld-Downloader&Date)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

This project is licensed under the **[MIT License](LICENSE)**.
For full terms and conditions, please see the LICENSE file included with this project.
