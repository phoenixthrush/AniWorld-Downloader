# AniWorld Downloader

## Project Discontinued

This project has been abandoned. The source remains available, and you're welcome to reuse it. If you're seeking an alternative, please consider visiting [Commandcracker's "gucken" repository](https://github.com/Commandcracker/gucken). Thank you.

## Description

AniWorld Downloader is a command-line tool designed to download content from aniworld.to. It offers various features, including fetching single episodes, downloading entire seasons, organizing downloads into structured directories, and supporting multiple operating systems.

## Usage

To use AniWorld Downloader, follow these steps:

1. Clone the repository to your local machine:
   `git clone https://github.com/phoenixthrush/AniWorld-Downloader.git`
3. Navigate to the project directory.
4. Set up a virtual environment:
   - On Unix/Linux/macOS:
     ```
     python3 -m venv venv
     source venv/bin/activate
     ```
   - On Windows:
     ```
     py -m venv venv
     venv\Scripts\activate
     ```
5. Install the required dependencies by running `pip install -r requirements.txt`.
3. Run the script using Python: `python main.py [options]`.

## Options

The available options include:

- `--link`: Aniworld.to link
- `--verbose`: Enable verbose mode for detailed output.
- `--download`: Enable download mode to download content.
- `--watch`: Enable watch mode to stream content.
- `--link_only`: Enable link-only mode to display the direct links.

## Todo

- [ ] Fix bug when only 2 languages available
- [ ] Create reusable functions inside `search_series()`
- [x] Skip downloading the binaries if already installed
- [ ] Add TOR proxy option
- [ ] Implement option to download whole seasons
- [ ] Implement option to download multiple seasons
- [ ] Add Anime4K option to arguments
- [x] Add search function to query series
- [x] Implement option to choose between dub and sub and language
- [x] Create subfolders for each season in the download directory
- [x] Implement multi-OS support (Windows, macOS, Linux/Unix)
- [ ] Test compatibility on Windows, macOS, and Linux/Unix

## Contributing

Contributions to AniWorld Downloader are welcome! Feel free to submit bug reports, feature requests, or pull requests to help improve the project.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
