# AniWorld Downloader v5

![AniWorld Downloader banner](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/aniworld-banner.png?raw=true)

![GitHub Release](https://img.shields.io/github/v/release/phoenixthrush/AniWorld-Downloader)
[![PyPI Downloads](https://static.pepy.tech/badge/aniworld)](https://pepy.tech/projects/aniworld)
![GitHub License](https://img.shields.io/github/license/phoenixthrush/AniWorld-Downloader)
[![Docker Image Size](https://ghcr-badge.egpl.dev/phoenixthrush/aniworld-downloader/size)](https://github.com/phoenixthrush/AniWorld-Downloader/pkgs/container/aniworld-downloader)
![GitHub Issues or Pull Requests](https://img.shields.io/github/issues/phoenixthrush/AniWorld-Downloader)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?logo=discord&logoColor=white)](https://discord.gg/BfDvrKd8V5)
[![PayPal Donate](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://www.paypal.com/paypalme/justnekochan)
![GitHub Repo stars](https://img.shields.io/github/stars/phoenixthrush/AniWorld-Downloader)
![GitHub forks](https://img.shields.io/github/forks/phoenixthrush/AniWorld-Downloader)

Find, download, and watch anime, movies, and series, or save manga chapters to read later. AniWorld Downloader brings supported sites together in a browser-based Web UI, with an interactive terminal menu and a CLI for scripts and automation.

It runs on **Windows, macOS, and Linux**, with **Docker** and standalone builds available too. Free and open source, with no ads, tracking, or paid-only features.

[Getting started](#quick-start) · [Supported sites](#supported-sites) · [Docker](#docker) · [Documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/) · [Python examples](examples)

![Interactive terminal menu](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/demo.png?raw=true)

https://github.com/user-attachments/assets/d65c4a5c-827a-45d7-a904-78977fd9aef4

## Quick Start

With **Python 3.11 or newer** installed:

```bash
python -m pip install -U aniworld
aniworld -w
```

Open [localhost:8080](http://localhost:8080) to use the Web UI. To start the interactive terminal menu instead:

```bash
aniworld
```

To install the latest development version from the `models` branch:

```bash
pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git@models
```

Video downloads need **FFmpeg**. Playback uses **mpv**, **IINA**, or **Syncplay**, depending on the action you choose. Portable dependencies can be installed automatically on Windows; macOS and Linux use system packages.

Prefer another installation method? Use [Docker](#docker) or download a standalone build from [GitHub Releases](https://github.com/phoenixthrush/AniWorld-Downloader/releases). See the [documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/) for platform-specific setup and troubleshooting.

## Features

- Download individual episodes, whole seasons or series, movies, and manga chapters.
- Search supported sites, track your download queue, and browse your library in the Web UI.
- Keep up with new episodes using Auto-Sync and release scheduling.
- Choose available audio and subtitle languages, with fallback to other stream hosters.
- Customize folders, filenames, and output formats, including MKV/MP4 for video and JPG/CBZ for manga.
- Watch through external players, with AniSkip and Anime4K support where applicable.

The Web UI also supports local accounts, optional OIDC SSO, custom CSS, and background shaders. A JSON API and optional Discord request bot let you connect it to other tools. Features and language availability vary by site.

## Supported Sites

AniWorld and SerienStream are the main focus of the project.

Last checked: **09/2026**. These statuses reflect sampled stream/image checks, not complete downloads or playback tests. Availability can vary by title, region, and stream hoster.

| Site | Content | Status | Notes |
| --- | --- | --- | --- |
| AniWorld | Anime and anime movies | Working | |
| SerienStream | Series | Working: captcha required | |
| MegaKino | Movies and series | Working | |
| Filmo | Movies | Working | |
| Moflix | Movies and series | Working | |
| MangaFire | Manga | Working | JPG and CBZ downloads |
| FilmPalast | Movies | Working | |
| Hanime | Adult animation | Working | Disabled by default |
| Kinox | Movies and series | Unverified: manual captcha required | Disabled by default |
| BurningSeries | Series | Broken: embed resolution failed | Disabled by default |
| Cineby | Movies and series | Unverified: stream API unavailable | Shut down; disabled by default |

### Stream Hosters

Sites list the titles; stream hosters provide the video links. The checks below use the same **09/2026** snapshot.

| Hoster | Status |
| --- | --- |
| VOE | Working |
| Filemoon | Working |
| Doodstream | Working |
| MegaKino | Working |
| Gupload | Working |
| MoflixClick | Working |
| Vidara | Working |
| Vidmoly | Broken: no embed HTML returned |
| Vidoza | Unverified: Shut down? |

If a hoster fails, the downloader can try others in your configured fallback order, provided the title offers them. Streamtape, Luluvdo, and LoadX are no longer implemented. VOE previews are broken; Filemoon, Doodstream, and MegaKino previews are not implemented.

## CLI Usage

Replace `SUPPORTED_URL` with an episode, season, series, movie, or chapter URL from a supported site:

```bash
aniworld "SUPPORTED_URL"
```

To choose a language and provider without opening the menu:

```bash
aniworld --no-menu --language "German Dub" --provider VOE "https://aniworld.to/anime/stream/example/staffel-1/episode-1"
```

For all options, more examples, or your installed version:

```bash
aniworld --help
aniworld --examples
aniworld --version
```

## Docker

Save [`docker-compose.yaml`](docker-compose.yaml) in a folder on your machine. From that folder, create the download directory and start the app:

```bash
mkdir -p Downloads
docker compose up -d
```

Open [localhost:8080](http://localhost:8080) when the container is ready. The image includes FFmpeg and Chromium for captcha handling.

- Downloads are saved to `./Downloads` on your machine.
- The `aniworld-data` volume keeps the database, `.env`, and custom themes across container recreation.
- Use `docker compose logs -f` to view logs and `docker compose down` to stop the app.

To update the image and restart:

```bash
docker compose pull
docker compose up -d
```

The Compose file includes configuration examples. Set persistent options in its `environment:` block, or load a host `.env` file using `env_file`. Settings marked *resets after restart* in the Web UI only affect the running process.

## Configuration and Integrations

Configuration lives in `~/.aniworld/.env` by default. Set `ANIWORLD_INSTALL_FOLDER` to change the app data directory. See [`src/aniworld/.env.example`](src/aniworld/.env.example) for available settings and defaults.

Many settings can be changed in the Web UI. Those marked *resets after restart* must also be set in your `.env` or deployment environment to persist. Saved themes, database records, and Discord bot settings are stored separately and survive restarts when the app data is retained.

**Optional integrations:** the standard installation includes the Web UI and terminal dependencies. Install an extra for OIDC login or Discord requests:

```bash
python -m pip install "aniworld[sso]"
python -m pip install "aniworld[discord]"
```

Use `"aniworld[all]"` to install both. The Docker image already includes them.

**API:** search, manage the queue, and access library and settings operations through JSON endpoints. Create a key in **Settings → API Keys**, then send it with your requests:

```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8080/api/queue
```

Keys have read, read-and-download, or full-access permissions. They cannot manage other API keys. The settings page includes an endpoint reference with examples.

**Appearance:** use **Settings → Appearance** for custom CSS and background shaders. The [`themes/`](themes) directory contains a light theme and a documented CSS template. To recover from a theme that hides controls, open `/settings?nocss=1`.

**Python:** the [`examples/`](examples) directory demonstrates site models, metadata, downloads, and genre queries. Backend capabilities can differ from what is exposed in the Web UI.

## Contributing

Bug reports, fixes, provider updates, and documentation improvements are welcome. Please check existing [issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) first. For a bug report, include your operating system, installation method, app and Python versions, the command or steps you used, and relevant logs.

To work on the current development branch:

```bash
git clone --branch models https://github.com/phoenixthrush/AniWorld-Downloader.git
cd AniWorld-Downloader
python -m pip install -e ".[all,test]"
pytest
```

Automated tests run without contacting live sites. Separate `tests/test_providers_*.py` scripts check live providers. CI also runs Ruff checks. Keep pull requests focused and explain what changed and how you tested it.

### Contributors

Thank you to everyone who reports issues, shares ideas, and contributes code.

<a href="https://github.com/phoenixthrush/AniWorld-Downloader/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=phoenixthrush/AniWorld-Downloader" alt="AniWorld Downloader contributors" />
</a>

### Credits

AniWorld Downloader uses [mpv](https://github.com/mpv-player/mpv), [IINA](https://github.com/iina/iina), [Syncplay](https://github.com/Syncplay/syncplay), [Anime4K](https://github.com/bloc97/Anime4K), [AniSkip](https://api.aniskip.com/api-docs), [flag-icons](https://github.com/lipis/flag-icons), [new-domain-check](https://github.com/Yezun-hikari/new-domain-check), and [fake-useragent](https://github.com/fake-useragent/fake-useragent).

### Other Cool Projects

- [Jellyfin-AniWorld-Downloader](https://github.com/SiroxCW/Jellyfin-AniWorld-Downloader) by SiroxCW — browse and download AniWorld content from Jellyfin.
- [AniSeerr](https://github.com/Yezun-hikari/AniSeerr) by Yezun-hikari — connect Seerr requests to AniWorld Downloader.
- [AniBridge](https://github.com/Zzackllack/AniBridge) by Zzackllack — connect supported catalogues to automation tools through FastAPI.
- [AniLoader](https://github.com/WimWamWom/AniLoader) by WimWamWom — a standalone web-based fork.

## Support and Community

For help, check the [documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/), open a [GitHub issue](https://github.com/phoenixthrush/AniWorld-Downloader/issues), or join us on [Discord](https://discord.gg/BfDvrKd8V5). You can also reach me at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com).

If the project has been useful, a star, a contribution, or a [donation](https://www.paypal.com/paypalme/justnekochan) is always appreciated. Thanks for being part of it. <3

## Legal Disclaimer

AniWorld Downloader is a client-side tool. It does not host, upload, store, or distribute media on behalf of third-party sites.

You are responsible for how you use it and for following the laws and terms that apply where you live. The project is provided "as is". Its maintainers are not responsible for third-party content, external links, or the availability, accuracy, legality, or reliability of outside services.

Questions about content hosted by another service should be directed to that service.

## Star History

<a href="https://www.star-history.com/?type=date&repos=phoenixthrush%2FAniWorld-Downloader">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=phoenixthrush/AniWorld-Downloader&type=date&theme=dark&legend=top-left&sealed_token=2w3mvLwCvYdC3Bq9vEfw-I3us7ocvtgOppVR5_etK2ZoymoZesVxuElMPDB0v_x46GEhBSkjWsN6bgleOwD5k0xC-LI-o4eh1Cq4iJAIRP-GBwweIiP7UqcOt7Vn9BjC_-Wv0iuJbxmfs8Xn2QAiwgq0TuOu5LLJkkbTleDugs-IwWF7ZYz5hvUPkc6-" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=phoenixthrush/AniWorld-Downloader&type=date&legend=top-left&sealed_token=2w3mvLwCvYdC3Bq9vEfw-I3us7ocvtgOppVR5_etK2ZoymoZesVxuElMPDB0v_x46GEhBSkjWsN6bgleOwD5k0xC-LI-o4eh1Cq4iJAIRP-GBwweIiP7UqcOt7Vn9BjC_-Wv0iuJbxmfs8Xn2QAiwgq0TuOu5LLJkkbTleDugs-IwWF7ZYz5hvUPkc6-" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=phoenixthrush/AniWorld-Downloader&type=date&legend=top-left&sealed_token=2w3mvLwCvYdC3Bq9vEfw-I3us7ocvtgOppVR5_etK2ZoymoZesVxuElMPDB0v_x46GEhBSkjWsN6bgleOwD5k0xC-LI-o4eh1Cq4iJAIRP-GBwweIiP7UqcOt7Vn9BjC_-Wv0iuJbxmfs8Xn2QAiwgq0TuOu5LLJkkbTleDugs-IwWF7ZYz5hvUPkc6-" />
 </picture>
</a>

## License

AniWorld Downloader is available under the [MIT License](LICENSE).
