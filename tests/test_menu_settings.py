"""Menu actions and paths follow separate settings, without opening curses."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld import menu


@pytest.fixture
def render_menu(monkeypatch):
    widgets = {}

    def add(widget_type, **kwargs):
        widget = SimpleNamespace(
            **kwargs,
            hidden=False,
        )
        widget.values = kwargs.get("values", [])
        widget.value = kwargs.get("value", [])
        widget.get_selected_objects = lambda: [
            widget.values[index] for index in widget.value
        ]
        widgets[kwargs["name"]] = widget
        return widget

    form = Mock()
    form.add.side_effect = add
    monkeypatch.setattr(menu, "QuitForm", lambda **kwargs: form)
    monkeypatch.setattr(menu.npyscreen, "setTheme", lambda theme: None)
    episode = SimpleNamespace(url="https://example.test/episode", provider_data={})
    season = SimpleNamespace(season_number=1, episodes=[episode])
    series = SimpleNamespace(title="Example", seasons=[season])
    monkeypatch.setattr(
        menu,
        "resolve_provider",
        lambda url: SimpleNamespace(name="AniWorld", series_cls=lambda url: series),
    )

    def render():
        app = menu.MenuApp("https://example.test/series")
        app.main()
        return app.result, widgets

    return render


@pytest.mark.parametrize(
    "restriction, expected_actions",
    [
        (None, ["Download", "Watch", "Syncplay"]),
        ("0", ["Download", "Watch", "Syncplay"]),
        ("1", ["Download"]),
    ],
)
@pytest.mark.parametrize(
    "path, relative, folder",
    [
        ("/app/Downloads", False, "app/Downloads"),
        ("/data/media", False, "data/media"),
        ("~/Videos", True, "Videos"),
        ("Videos", True, "Videos"),
        ("   ", True, "Downloads"),
        ("", True, "Downloads"),
        (None, True, "Downloads"),
    ],
)
def test_menu_restriction_is_independent_of_save_location(
    monkeypatch,
    tmp_path,
    render_menu,
    restriction,
    expected_actions,
    path,
    relative,
    folder,
):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    if path is None:
        monkeypatch.delenv("ANIWORLD_DOWNLOAD_PATH", raising=False)
    else:
        monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", path)
    if restriction is None:
        monkeypatch.delenv("ANIWORLD_MENU_DOWNLOAD_ONLY", raising=False)
    else:
        monkeypatch.setenv("ANIWORLD_MENU_DOWNLOAD_ONLY", restriction)

    result, widgets = render_menu()
    assert widgets["Action"].values == expected_actions
    # A rooted path without a drive keeps the home drive on Windows.
    base = home if relative else Path(home.anchor)
    expected_path = base / folder
    assert widgets["Save Location"].value == expected_path
    assert result["path"] == expected_path
    assert result["action"] == "Download"


def test_menu_preserves_native_absolute_save_location(
    monkeypatch, tmp_path, render_menu
):
    destination = tmp_path / "media"
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(destination))
    monkeypatch.setenv("ANIWORLD_MENU_DOWNLOAD_ONLY", "1")

    result, widgets = render_menu()
    assert widgets["Save Location"].value == destination
    assert result["path"] == destination
