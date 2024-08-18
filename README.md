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

## Usage

To run AniWorld Downloader, use this command:

```shell
aniworld
```

If you want to directly pass the options without using the menu, you can use the arguments. For example:
```
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1
```

To enable the --keep-watching option and automatically play the next episode after the one you specified, use:
```
aniworld --episode https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1 --keep-watching
```

Alternatively, you can specify only the query:
```
aniworld --query food --keep-watching
```

Or with spaces:
```
aniworld --query "food wars" --keep-watching
```

This will start playing the specified episode and continue to the next episode automatically.

To see all the available options, run this command:
```
aniworld --help
```

## TODO

- [x] Utilize argparse for command-line argument parsing
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
