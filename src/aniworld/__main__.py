import ctypes
import platform

from aniworld.entry import aniworld
from aniworld.config import VERSION


def main():
    if platform.system() == "Windows":
        ctypes.windll.kernel32.SetConsoleTitleW(
            f"AniWorld-Downloader {VERSION}"
        )

    aniworld()


if __name__ == "__main__":
    main()
