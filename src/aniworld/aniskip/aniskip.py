import shutil
import tempfile
from pathlib import Path

try:
    from ..config import GLOBAL_SESSION, MPV_SCRIPTS_DIR, logger
    # from .jikan import get_all_seasons_by_query
except ImportError:
    # from aniworld.aniskip import get_all_seasons_by_query
    from aniworld.config import GLOBAL_SESSION, MPV_SCRIPTS_DIR, logger

ANISKIP_API_URL = "https://api.aniskip.com/v1/skip-times/{}/{}?types=op&types=ed"


def setup_aniskip():
    """
    Copy AniSkip Lua scripts (aniskip.lua, autoexit.lua, autostart.lua)
    to the mpv scripts directory, only if they don't already exist.
    """

    # Source folder where your Lua scripts are stored
    src_dir = Path(__file__).parent / "scripts"
    scripts_to_copy = ["aniskip.lua", "autoexit.lua", "autostart.lua"]

    # Ensure the scripts directory exists
    MPV_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy each Lua script if it doesn't exist in the destination
    for script in scripts_to_copy:
        src_path = src_dir / script
        dest_path = MPV_SCRIPTS_DIR / script

        if not src_path.exists():
            logger.warning(f"[WARNING] Script not found: {src_path}")
            continue

        if not dest_path.exists():
            shutil.copy2(src_path, dest_path)
            logger.debug(f"[COPIED] {script} -> {MPV_SCRIPTS_DIR}")
        else:
            logger.debug(f"[SKIPPED] {script} already exists in {MPV_SCRIPTS_DIR}")

    logger.debug("[SETUP COMPLETE] AniSkip scripts are ready in mpv scripts directory.")


def get_skip_times(mal_id: int, episode_number: int):
    url = ANISKIP_API_URL.format(mal_id, episode_number)
    res = GLOBAL_SESSION.get(url)
    if res.status_code == 200:
        return res.json()
    return None


def ftoi(seconds: float) -> int:
    """Convert seconds to milliseconds as integer."""
    return round(seconds * 1000)


def build_mpv_flags(skip_data) -> str:
    """
    Build MPV command flags based on AniSkip API response.
    Returns a string with --chapters-file and --script-opts options.
    """
    if not skip_data or skip_data.get("found") is not True:
        return ""

    options_list = []
    with tempfile.NamedTemporaryFile("w", delete=False) as chapters_file:
        chapters_file.write(";FFMETADATA1\n")
        for entry in skip_data.get("results", []):
            st = entry["interval"]["start_time"]
            ed = entry["interval"]["end_time"]
            skip_type = entry["skip_type"]  # 'op' or 'ed'
            chapters_file.write(
                f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={ftoi(st)}\nEND={ftoi(ed)}\nTITLE={skip_type.upper()}\n"
            )
            options_list.append(
                f"skip-{skip_type}_start={st},skip-{skip_type}_end={ed}"
            )

    options_str = ",".join(options_list)

    return f"--chapters-file={chapters_file.name} --script-opts={options_str}"


if __name__ == "__main__":
    setup_aniskip()

    """
    query = "Highschool DxD"

    mal_ids = get_all_seasons_by_query(query)

    print(f"Found {len(mal_ids)} seasons for '{query}':\n")

    for idx, mal_id in enumerate(mal_ids, start=1):
        print(f"{idx}. MAL ID: {mal_id}")

        episode_number = 1
        skip_times = get_skip_times(mal_id, episode_number)

        try:
            mpv_flags = build_mpv_flags(skip_times)
            print("  MPV command flags:")
            print(f"    {mpv_flags}\n")
        except ValueError as e:
            print(f"  Error building MPV flags: {e}\n")
    """
