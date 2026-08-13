import json

from aniworld.models import (
    AniworldEpisode,
    AniworldSeason,
    AniworldSeries,
    BurningSeriesSeries,
    FilmPalastEpisode,
    KinoxSeries,
    SerienstreamEpisode,
    SerienstreamSeason,
    SerienstreamSeries,
)

RED = "\033[31m"
RESET = "\033[0m"


def object_to_json(obj):
    cls = obj.__class__
    mangled_prefix = f"_{cls.__name__}__"
    data = {}
    for name in vars(obj):
        clean_name = name.removeprefix(mangled_prefix)
        if clean_name.startswith(("_series", "_season", "html")):
            continue
        value = getattr(obj, clean_name, None)
        try:
            json.dumps(value)
            data[clean_name] = value
        except TypeError:
            data[clean_name] = str(value)
    return data


def print_colored_json(obj_data):
    lines = []
    for key, value in obj_data.items():
        json_key = json.dumps(key, ensure_ascii=False)
        if value is None:
            json_value = f"{RED}null{RESET}"
        else:
            json_value = json.dumps(value, ensure_ascii=False)
        lines.append(f"    {json_key}: {json_value}")
    print("{\n" + ",\n".join(lines) + "\n}")


def check_model_serialization(cls, url):
    obj = cls(url)
    obj_data = object_to_json(obj)
    print(f"Test: {cls.__name__}\nURL: {url}\nResult:")
    print_colored_json(obj_data)
    print("=" * 80)
    output_str = json.dumps(obj_data, ensure_ascii=False)
    assert output_str.strip().startswith("{"), "Output should be JSON"
    assert url in output_str, f"URL should appear in JSON output for {cls.__name__}"


def run_all_tests():
    tests = [
        (AniworldSeries, "https://aniworld.to/anime/stream/highschool-dxd"),
        (AniworldSeason, "https://aniworld.to/anime/stream/highschool-dxd/staffel-1"),
        (
            AniworldEpisode,
            "https://aniworld.to/anime/stream/highschool-dxd/staffel-1/episode-1",
        ),
        (
            SerienstreamSeries,
            "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir",
        ),
        (
            SerienstreamSeason,
            "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1",
        ),
        (
            SerienstreamEpisode,
            "https://serienstream.to/serie/american-horror-story-die-dunkle-seite-in-dir/staffel-1/episode-1",
        ),
        # New sites (contributed): movie + series entry points
        (FilmPalastEpisode, "https://filmpalast.to/stream/scream-7"),
        (KinoxSeries, "https://kinox.to/Stream/Avatar-Der_Herr_der_Elemente.html"),
        (BurningSeriesSeries, "https://bs.to/serie/Breaking-Bad"),
    ]
    all_passed = True
    for cls, url in tests:
        try:
            check_model_serialization(cls, url)
        except AssertionError as e:
            print(f"Assertion failed for {cls.__name__}: {e}")
            all_passed = False
    if all_passed:
        print("All tests passed successfully.")
    else:
        print("Some tests failed.")


if __name__ == "__main__":
    run_all_tests()
