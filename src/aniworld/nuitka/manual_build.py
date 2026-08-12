import subprocess


def build():
    subprocess.run(
        [
            "python",
            "-m",
            "nuitka",
            "src/aniworld",
        ],
        check=False,
    )


if __name__ == "__main__":
    build()
