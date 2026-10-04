"""Regression checks for configuration rendered into the Web UI."""

import json
import re

import pytest


def _site_config(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    config = re.search(
        r'<script id="site-config" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert config is not None
    return json.loads(config.group(1))


@pytest.mark.parametrize(
    ("site", "languages"),
    [
        ("aniworld", ["German Dub", "English Sub", "German Sub", "English Dub"]),
        ("sto", ["German Dub", "English Dub"]),
        ("megakino", ["German Dub"]),
    ],
)
def test_home_renders_site_languages(client, site, languages):
    settings = _site_config(client)
    assert settings["SITE_LANGUAGES"][site] == languages
    assert settings["DEFAULT_LANGUAGE"] == "German Dub"
    assert settings["AUTOSYNC_ENABLED"] is False
    assert "VOE" in settings["STATIC_PROVIDERS"]


def test_home_filters_languages_by_default(client):
    settings = _site_config(client)
    assert settings["SHOW_ALL_LANGUAGES"] is False
    assert settings["ENGLISH_SUB_DISABLED"] is False


def test_home_offers_every_language_when_asked(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_SHOW_ALL_LANGUAGES", "1")
    monkeypatch.setenv("ANIWORLD_DISABLE_ENGLISH_SUB", "1")
    settings = _site_config(client)
    assert settings["SHOW_ALL_LANGUAGES"] is True
    # The page still has to drop English Sub itself, the probe no longer does
    assert settings["ENGLISH_SUB_DISABLED"] is True
