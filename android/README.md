# AniApp

**AniApp** is a native Android app for [AniWorld Downloader](https://github.com/phoenixthrush/AniWorld-Downloader):
browse, search, stream and download on your phone, without a PC, Python or FFmpeg.
The look and wording follow the project's Web UI (dark theme, Inter, site switcher, queue, library).
The interface is available in English and German and follows the phone's language.

> The app is a standalone Kotlin/Jetpack Compose port. Python, FFmpeg and Chromium don't run on Android,
> so the logic from `src/aniworld/` is reimplemented rather than embedded.

## Features

| | |
|---|---|
| **Sites** | AniWorld (anime), SerienStream (series, falls back to serienstream.cx), Burning Series, Kinox, MegaKino, Moflix, Filmo and FilmPalast, switchable at the top |
| **Home** | Spotlight, popular and new titles, new episodes, genres, recently opened, “Random” (AniWorld) |
| **Search** | all sites at once, results grouped by site |
| **Series** | cover, description, seasons and movies, one language for the whole series, tick episodes and “Download selected” |
| **Languages** | German dub, German sub, English sub, English dub, with the Web UI's flag badges |
| **Streaming** | built-in player (Media3) with resume, next episode and AniSkip (“Skip opening”) |
| **Downloads** | single episodes, a selection, whole seasons or series; runs in the background with pause and resume |
| **Hosters** | VOE, Filemoon/Byse, Doodstream, Vidoza, Vidmoly, GXPlayer (MegaKino), MoflixClick; configurable order, falls back to the next one |
| **Queue** | filters (downloading, queued, paused, failed) with counters, progress, retry all failed |
| **Library** | finished series and movies as posters, continue watching, delete |
| **Auto-Sync** | checks series in the library every 6, 12 or 24 hours and queues newly released episodes in the language last downloaded |
| **Links** | links to any of the sites open directly in the app (also via “Share”) |

Files are stored like the desktop version does, below `Movies/AniWorld/` (changeable in the settings):

```
Movies/AniWorld/<Series>/Staffel 01/<Series> S01E01.mp4
Movies/AniWorld/<Series>/Filme/<Series> Film 01.mp4
Movies/AniWorld/Filme/<Title (Year)>.mp4          ← single movies (Filmo, FilmPalast, Kinox, MegaKino, Moflix)
```

## Installation

Requires Android 8 or newer.

1. Install the APK (allow installing from unknown sources once).
2. On first start a short setup explains and asks for each permission; every step can be skipped and
   repeated later under **Settings → Help → Setup**:
   - **Notifications** (Android 13 and newer ask), otherwise running downloads are invisible.
   - **Storage access**, otherwise files end up in `Android/media/<package>/`. From Android 11 on this is
     “All files access”, before that the normal storage permission.
   - **Battery optimization** off. Many vendors (OnePlus, Xiaomi, Samsung) kill long background downloads otherwise.

Protection pages (DDoS-Guard, Cloudflare, Kinox' verification) are handled in a visible browser window:
if a challenge shows up, solve it once and the app continues with the same cookies. The app never tries to
get past such a check on its own; Auto-Sync skips a site that asks for one and tries again next time.

Auto-Sync is off by default. When a series is checked for the first time it only remembers what is already
online, so downloading a single sample episode never pulls in a whole back catalogue.

## Building

Needs JDK 17 and the Android SDK 34 (e.g. from Android Studio).

```bash
cd android
./gradlew assembleRelease      # app/build/outputs/apk/release/app-release.apk
./gradlew testDebugUnitTest    # parser, hoster, HLS and AniSkip tests (offline, against saved pages)
./gradlew lintDebug
```

Release builds are signed with the debug key unless a `keystore.properties` file next to this README provides
`storeFile`, `storePassword`, `keyAlias` and `keyPassword`.

`targetSdk` stays at 34 on purpose: from 35 on, Android limits `dataSync` foreground services to six hours a day,
which would cut long season downloads short.

## How it maps to the Python code

| Python | App |
|---|---|
| `models/aniworld_to/`, `search.py` | `site/AniWorldParser.kt`, `site/AniWorld.kt` |
| `models/s_to/` | `site/SerienStreamParser.kt`, `site/SerienStream.kt` (mirror fallback like `http.py`) |
| `models/filmo_to/` | `site/FilmoParser.kt`, `site/Filmo.kt` (source tokens via `/n` like `redirect_url`) |
| `models/burningseries/` | `site/BurningSeriesParser.kt`, `site/BurningSeries.kt` |
| `models/kinox/`, `query_kinox()` | `site/KinoxParser.kt`, `site/Kinox.kt` |
| `models/megakino/` | `site/MegaKinoParser.kt`, `site/MegaKino.kt` (domain from the same tracker) |
| `models/moflix_stream/` | `site/MoflixParser.kt`, `site/Moflix.kt` |
| `models/filmpalast_to/`, `query_filmpalast()` | `site/FilmPalastParser.kt`, `site/FilmPalast.kt` |
| `web/autosync.py` | `download/AutoSync.kt` (WorkManager) |
| `aniskip/` | `site/AniSkip.kt` and the skip button in the player |
| `config.py` (`GLOBAL_SESSION`, DoH) | `net/Netz.kt`: OkHttp with DNS over HTTPS, cookies shared with the WebView |
| `playwright/captcha.py` | `net/BrowserCheck.kt`, `ui/BrowserFenster.kt` |
| `extractors/provider/` | `hoster/Voe.kt`, `Filemoon.kt`, `Doodstream.kt`, `Vidoza.kt`, `Vidmoly.kt`, `GxPlayer.kt`, `MoflixClick.kt` |
| – | `hoster/Mitleser.kt`: fallback that opens the hoster in a hidden WebView and captures the video URL |
| `models/common/hls.py` + FFmpeg | `download/Hls.kt`, `Lader.kt` (parallel segments, AES-128, fMP4), `Umpacker.kt` (TS → MP4 via MediaMuxer) |
| Web UI queue and library | `download/Datenbank.kt` (SQLite), `DownloadService.kt`, `ui/DownloadsSeite.kt` |
| Web UI `style.css` | `ui/Thema.kt` (colors, type), `ui/Bausteine.kt` (cards, pills, language badges) |

New sites implement `site/Anbieter.kt` (home, search, genre, series, season, links, redirect);
new hosters implement `hoster/Hoster.kt`. UI texts live in `res/values/strings.xml` (English) and
`res/values-de/strings.xml` (German).

## Limitations

- Of the desktop version's sites, MangaFire (manga) and the adult sites are missing.
- Burning Series, Kinox and Moflix often need a browser check or a VPN before the hoster opens.
- No Syncplay and no separate subtitle files.
- When something fails, **Settings → Log → Copy** gives the details for an issue.

## Licenses

App code under the project's license. Inter: SIL Open Font License (`lizenzen/Inter-OFL.txt`).
Flags from [flag-icons](https://github.com/lipis/flag-icons): MIT (`lizenzen/flag-icons-MIT.txt`).
The site icons in `res/drawable-nodpi/logo_*.png` are the sites' own favicons, used only to tell the sites apart;
they belong to their respective owners.
