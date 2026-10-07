# AniWorld Downloader v5

![AniWorld Downloader banner](https://github.com/phoenixthrush/AniWorld-Downloader/blob/models/.github/assets/aniworld-banner.png?raw=true)

![GitHub Release](https://img.shields.io/github/v/release/phoenixthrush/AniWorld-Downloader)
[![PyPI Downloads](https://static.pepy.tech/badge/aniworld)](https://pepy.tech/projects/aniworld)
![GitHub License](https://img.shields.io/github/license/phoenixthrush/AniWorld-Downloader)
[![Docker Image Size](https://ghcr-badge.egpl.dev/phoenixthrush/aniworld-downloader/size)](https://github.com/phoenixthrush/AniWorld-Downloader/pkgs/container/aniworld-downloader)
![GitHub Issues or Pull Requests](https://img.shields.io/github/issues/phoenixthrush/AniWorld-Downloader)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?logo=discord&logoColor=white)](https://discord.gg/BfDvrKd8V5)
[![GitHub Sponsors](https://img.shields.io/badge/♥%20Sponsor-Visit-red)](https://github.com/sponsors/phoenixthrush)
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

Video downloads need **FFmpeg**. Playback uses **mpv**, **IINA**, or **Syncplay**, depending on the action you choose. The app offers to install missing portable tools on Windows or system packages on macOS/Linux. You can also install them yourself; unattended deployments should provide the tools in advance.

Prefer another installation method? Use [Docker](#docker) or download a standalone build from [GitHub Releases](https://github.com/phoenixthrush/AniWorld-Downloader/releases). See the [documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/) for platform-specific setup and troubleshooting.

## Features

- Download individual episodes, whole seasons or series, movies, and manga chapters.
- Search supported sites, track your download queue, and browse your library in the Web UI.
- Schedule Auto-Sync checks for AniWorld titles already downloaded to your library.
- Choose available audio and subtitle languages, with fallback to other stream hosters.
- Customize supported naming templates and output formats, including MKV/MP4 for video and JPG/CBZ for manga; naming support varies by backend.
- Watch through external players, with AniSkip and Anime4K support where applicable.

The Web UI also supports local accounts, optional OIDC SSO, custom CSS, and background shaders. SSO alongside local login requires both `--web-auth` and `--web-sso`; `--web-force-sso` enables SSO-only authentication. A JSON API and optional Discord request bot let you connect it to other tools. Features and language availability vary by site.

For CAPTCHA browser visibility, manual solving, timeouts, and debug logs, see [CAPTCHA configuration](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/configuration#captcha-solving).

## Supported Sites

AniWorld and SerienStream are the main focus of the project.

All registered source backends were checked live in **10/2026** using the manual provider scripts. The tables show the best observed results. Successful checks resolved sample stream or chapter/page URLs; no complete media files were downloaded. Results can vary by title, connection, and stream hoster.

| Site | Content | Status | Notes |
| --- | --- | --- | --- |
| AniWorld | Anime and anime movies | Stream URLs resolved | VOE, Doodstream, and Filemoon samples passed; Vidmoly failed |
| SerienStream | Series | Stream URLs resolved | VOE and Doodstream samples passed |
| MegaKino | Movies and series | Stream URLs resolved | VOE and the MegaKino hoster passed |
| Filmo | Movies | Stream URLs resolved | VOE samples passed |
| Moflix | Movies and series | Stream URL resolved | MoflixClick sample passed |
| MangaFire | Manga | Chapter/page URLs resolved | JPG and CBZ downloads supported |
| FilmPalast | Movies | Stream URL resolved | VOE sample passed |
| Hanime | Adult animation | Stream URL resolved | Disabled by default |
| HentaiTV | Adult animation | Stream and poster URLs resolved | Optional Web UI tab; disabled by default |
| AnimeIDHentai | Adult animation | Stream and poster URLs resolved | CLI/Python only |
| HentaiHaven | Adult animation | Stream and poster URLs resolved | Optional Web UI tab; disabled by default |
| Kinox | Movies and series | Blocked by verification CAPTCHA | Disabled by default |
| BurningSeries | Series | Stream mirrors returned VPN warning pages | Disabled by default |

"Disabled by default" refers to Web UI visibility; direct CLI URLs remain accepted. Hanime (`hanime.tv`), HentaiTV (`hentai.tv`) and HentaiHaven (`hentaihaven.xxx`) have optional Web UI tabs, enabled with `ANIWORLD_ENABLE_HTV=1`, `ANIWORLD_ENABLE_HENTAITV=1` and `ANIWORLD_ENABLE_HENTAIHAVEN=1`. AnimeIDHentai (`animeidhentai.com`) supports direct CLI URLs and Python use. See [adult-site usage](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/usage#adult-site-backends) for examples.

### Stream Hosters

Sites list the titles; stream hosters provide the video links. These results use the same **10/2026** checks, including fresh embed URLs discovered from current titles.

| Hoster | Stream extraction | Preview extraction |
| --- | --- | --- |
| VOE | Samples passed | Samples failed |
| Filemoon | Samples passed | Not implemented |
| Doodstream | Samples passed | Not implemented |
| MegaKino | Sample passed | Not implemented |
| Gupload | Hostname did not resolve during the check | Not implemented |
| MoflixClick | Sample passed | Not implemented |
| Vidara | Kinox CAPTCHA prevented resolving the sample embed | Not implemented |
| Vidmoly | Samples failed: no embed HTML returned | Samples failed |
| Vidoza | Sample URL returned HTTP 404 | Sample URL returned HTTP 404 |

If a hoster fails, the downloader can try others in your configured fallback order, provided the title offers them in the selected language. It does not automatically switch languages. A failed or missing sample does not establish that a hoster has shut down. See [live provider checks](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/contributing#live-provider-checks) to repeat these checks.

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

Open [localhost:8080](http://localhost:8080) when the container is ready. The image includes FFmpeg and Chromium for captcha handling. Chromium setup runs only when an operation needs a browser and reuses an existing installation.

The terminal menu in the Docker image offers only Download and uses your configured download folder.

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

**Python:** all public site models are available from `aniworld` or `aniworld.models`. Search and genre functions share `aniworld.search`; see [Genre Search](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/genre-search) for supported filters and site limits. The [`examples/`](examples) directory demonstrates models, metadata, downloads, and genre queries.

## Contributing

Bug reports, fixes, provider updates, and documentation improvements are welcome. Please check existing [issues](https://github.com/phoenixthrush/AniWorld-Downloader/issues) first. For a bug report, include your operating system, installation method, app and Python versions, the command or steps you used, and relevant logs.

To work on the current development branch:

```bash
git clone --branch models https://github.com/phoenixthrush/AniWorld-Downloader.git
cd AniWorld-Downloader
python -m pip install -e ".[all,test]"
pytest
```

Automated tests run offline. See the [testing guide](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/contributing) for automated tests and live provider checks. CI also runs Ruff checks. Keep pull requests focused and explain what changed and how you tested it.

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
- [AniLoader](https://github.com/WimWamWom/AniLoader) by WimWamWom — a web-based download manager with automation.

## Support and Community

For help, check the [documentation](https://www.phoenixthrush.com/AniWorld-Downloader-Docs/), open a [GitHub issue](https://github.com/phoenixthrush/AniWorld-Downloader/issues), or join us on [Discord](https://discord.gg/BfDvrKd8V5). You can also reach me at [contact@phoenixthrush.com](mailto:contact@phoenixthrush.com).

If the project has been useful, a star, a contribution, or a [donation](https://github.com/sponsors/phoenixthrush) is always appreciated. Thanks for being part of it. <3

## Legal Disclaimer

AniWorld Downloader is a client-side tool that saves downloads to locations you choose. It does not operate a media-hosting service for third-party sites.

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
