import platform
import random
import re
from pathlib import Path


def __load_ascii_content():
    """Load the contents of the ASCII.txt file."""
    ascii_file = Path(__file__).parent / "ASCII.txt"
    with open(ascii_file, encoding="utf-8") as f:
        return f.read()


def __parse_ascii_blocks():
    """Parse ASCII content into categorized blocks."""
    content = __load_ascii_content()
    pattern = r"=== (banner|art|traceback): (\w+) ===\s*\n([\s\S]*?)(?=^=== (?:banner|art|traceback): |\Z)"
    matches = re.findall(pattern, content, flags=re.MULTILINE)

    blocks = {"banner": [], "art": [], "traceback": [], "all": []}
    for block_type, _, block in matches:
        cleaned = block.strip("\n")
        if cleaned:
            blocks[block_type].append(cleaned)
            blocks["all"].append(cleaned)

    return blocks


def __is_windows_legacy():
    """Return True if the system is Windows older than version 11."""
    if platform.system() != "Windows":
        return False
    try:
        return int(platform.release()) < 11
    except Exception:
        return True


def __random_block(blocks, fallback):
    """Return a random block from blocks or fallback if empty."""
    if blocks:
        return random.choice(blocks)
    if fallback:
        return random.choice(fallback)
    return ""


def display_ascii_art():
    """Return a random ASCII art string appropriate for the system."""
    blocks = __parse_ascii_blocks()
    if platform.system() == "Windows" and __is_windows_legacy():
        print(__random_block(blocks["banner"], fallback=blocks["all"]), flush=True)
        return
    print(__random_block(blocks["art"], fallback=blocks["all"]), flush=True)


def display_banner_art():
    """Return a random banner ASCII art string."""
    blocks = __parse_ascii_blocks()
    print(__random_block(blocks["banner"]), flush=True)


def display_traceback_art():
    """Return a random traceback ASCII art string."""
    blocks = __parse_ascii_blocks()
    print(__random_block(blocks["traceback"]), flush=True)


if __name__ == "__main__":
    display_ascii_art()
