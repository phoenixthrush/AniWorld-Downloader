import subprocess


def build():
    subprocess.run(
        [
            "python",
            "-m",
            "nuitka",
            "src/aniworld",
        ]
    )


if __name__ == "__main__":
    build()
