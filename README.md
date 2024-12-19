<a id="readme-top"></a>
# AniWorld Downloader

AniWorld Downloader is a command-line tool for downloading and streaming anime, series and movies, compatible with Windows, macOS, and Linux.

![Downloads](https://img.shields.io/pypi/dm/aniworld?label=Downloads&color=blue)
![License](https://img.shields.io/pypi/l/aniworld?label=License&color=blue)

![AniWorld Downloader - Demo](https://github.com/phoenixthrush/AniWorld-Downloader/blob/next/.github/assets/demo.png?raw=true)

### Installation (Requires Git)

- To install the latest version from GitHub, run:

```shell
pip install --upgrade git+https://github.com/phoenixthrush/AniWorld-Downloader.git@next#egg=aniworld
```

- To update, simply rerun the above command. These builds may be unstable, so it’s good to check regularly.

### Roadmap

- [ ] Fix subprocess commands in Watch, Download, Syncplay
- [ ] Fix None title of anime -> probably fixes get_mal_id_from_title crash
- [ ] Add automatic mpv, syncplay pull
- [ ] Add Anime4K support
- [ ] Add syncplay room options
- [ ] Add episode file support
- [ ] Speedup everything by not autofilling yet unnecessary vars in classes
- [ ] Add proxy support
- [ ] Add playwright support