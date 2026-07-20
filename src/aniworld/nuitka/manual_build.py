import subprocess


def build():
    subprocess.run(
        [
            "python",
            "-m",
            "nuitka",
            "src/aniworld",
            "--include-data-file=src/aniworld/browsers.jsonl=aniworld/browsers.jsonl",
        ]
    )


if __name__ == "__main__":
    build()
