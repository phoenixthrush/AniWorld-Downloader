"""Regression checks for configuration rendered into the Web UI."""

import json
import re

import pytest


@pytest.mark.parametrize(
    ("site", "languages"),
    [
        ("aniworld", ["German Dub", "English Sub", "German Sub", "English Dub"]),
        ("sto", ["German Dub", "English Dub"]),
        ("megakino", ["German Dub"]),
    ],
)
def test_home_renders_site_languages(client, site, languages):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    config = re.search(
        r'<script id="site-config" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert config is not None
    settings = json.loads(config.group(1))
    assert settings["SITE_LANGUAGES"][site] == languages
    assert settings["DEFAULT_LANGUAGE"] == "German Dub"
    assert settings["AUTOSYNC_ENABLED"] is False
    assert "VOE" in settings["STATIC_PROVIDERS"]
