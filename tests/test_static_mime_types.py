"""Static assets have to be served as something a browser will execute.

The app sends X-Content-Type-Options: nosniff on every response, so a wrong
Content-Type is not cosmetic: the browser refuses the file outright. Werkzeug
takes that type from the stdlib mimetypes table, which is seeded from the
machine, and installs do exist in the wild where .js is mapped to text/plain.
When that happens every script and the stylesheet are blocked, the home page
renders as bare HTML with every browse row showing at once, and no button
does anything -- while the network tab shows a row of unremarkable 200s.
"""

import mimetypes
import os
import subprocess
import sys
import textwrap

from aniworld.web import app as web_app

EXECUTABLE_JS = ("text/javascript", "application/javascript")


def content_type(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return response.headers["Content-Type"].split(";")[0].strip()


def test_scripts_are_served_as_javascript(client):
    for name in ("home.js", "i18n.js", "common.js", "settings.js"):
        assert content_type(client, f"/static/{name}") in EXECUTABLE_JS


def test_the_stylesheet_is_served_as_css(client):
    assert content_type(client, "/static/style.css") == "text/css"


def test_a_machine_that_calls_js_text_plain_cannot_break_the_ui(monkeypatch, client):
    """The whole point of pinning the types at import.

    monkeypatch.setitem restores the entry afterwards, so this cannot leak the
    broken mapping into another test.
    """
    monkeypatch.setitem(mimetypes.types_map, ".js", "text/plain")
    monkeypatch.setitem(mimetypes.types_map, ".css", "text/plain")
    web_app._register_mime_types()

    assert content_type(client, "/static/home.js") in EXECUTABLE_JS
    assert content_type(client, "/static/style.css") == "text/css"


def test_nosniff_is_what_makes_the_type_load_bearing(client):
    """If this header ever goes away the tests above stop mattering."""
    response = client.get("/static/home.js")
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_importing_the_web_app_repairs_a_broken_machine_table(tmp_path):
    """The import-time wiring, not just the function on its own.

    This needs a fresh interpreter. By the time this module is imported the
    repair has already run, so an in-process check cannot tell a repaired
    table apart from a machine that was fine to begin with -- it would pass
    just as happily with the wiring deleted. The subprocess poisons the table
    the way a bad registry would, before anything imports the app.
    """
    script = textwrap.dedent(
        """
        import mimetypes

        mimetypes.add_type("text/plain", ".js")
        mimetypes.add_type("text/plain", ".css")
        assert mimetypes.guess_type("x.js")[0] == "text/plain", "poison failed"

        import aniworld.web.app  # noqa: F401

        print(mimetypes.guess_type("x.js")[0], mimetypes.guess_type("x.css")[0])
        """
    )
    env = dict(os.environ, ANIWORLD_INSTALL_FOLDER=str(tmp_path / "config"))
    finished = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.split() == ["text/javascript", "text/css"]
