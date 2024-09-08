# AniWorld Downloader
![PyPI - Downloads](https://img.shields.io/pypi/dm/aniworld?color=blue)

## Description

AniWorld Downloader is a command-line tool for downloading and streaming content from aniworld.to.<br>
It can fetch single episodes, download entire seasons, and organize downloads into folders.<br><br>
This tool works on Windows, macOS, and Linux.

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/module/.github/demo.png?raw=true)

## Installation

To install AniWorld Downloader, use this command:

```shell
pip install aniworld
```

To update AniWorld Downloader, use this command:

```shell
pip install -U aniworld
```

To uninstall, use this command:
```shell
pip uninstall aniworld -y
```

## Usage

To run AniWorld Downloader, use this command:

```shell
aniworld
```

## Command Line Examples
### Watch

If you want to directly pass the options without using the menu, you can use the arguments. For example:
```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

To enable the --keep-watching option and automatically play the next episode after the one you specified, use:
```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --keep-watching
```

To quit keep-watching, pause the video, then go to the terminal and press CTRL + C twice.

Alternatively, you can specify only the query:
```shell
aniworld --query food --keep-watching
```

Or with spaces:
```shell
aniworld --query "food wars" --keep-watching
```

This will start playing the specified episode and continue to the next episode automatically.

### Download

For the best experience when downloading, I recommend using VOE since it downloads really fast (concurrently) by using all your bandwidth.

To download every episode of the anime, use:
```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --keep-watching --action Download --provider VOE
```

To download specific episodes of the anime, use:
```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-2 https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-3 --action Download --provider VOE
```

### Syncplay

To use SyncPlay, ensure both ends specify the same episode. It's best to use the same command as the other person or people, but it's not crucial. One person can use the query argument while the other uses the episode argument for example. It also works if different providers or languages are used. As long as the episode is the same, SyncPlay will function correctly. For example:
```shell
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --action Syncplay --keep-watching
```

### Help

To see all the available options, run this command:
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

## TODO

- [x] Utilize argparse for command-line argument parsing
- [ ] Instead of copying lua files append as parameter
- [ ] Do not show whole link in selection rather season and episode with name
- [ ] Refactor code into modular Python files
- [ ] Add proxy support
- [ ] Fix Aniskip finding wrong timestamps
- [ ] Fix wrong episode count on keep-watching per season
- [ ] Configure Anime4K installation setup
- [ ] Fix aniskip finding wrong MAL ID
- [ ] Integrate Python logging module
- [ ] Support Doodstream

## Contributing

Contributions to AniWorld Downloader are welcome!<br>
Feel free to submit bug reports, feature requests, or pull requests to help improve the project.

## Credits

- mpv - https://github.com/mpv-player/mpv.git
- yt-dlp - https://github.com/yt-dlp/yt-dlp.git
- syncplay - https://github.com/Syncplay/syncplay.git

## License

This project is licensed under the MIT License.<br>
See the LICENSE file for more details.<br>

Thank you for using AniWorld Downloader!
