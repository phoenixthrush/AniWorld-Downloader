"""Custom CSS: storage, the served stylesheet, and where it must not appear."""

import re
from pathlib import Path

import pytest

from aniworld.web import db, theming

REPO = Path(__file__).resolve().parent.parent
STYLE = REPO / "src" / "aniworld" / "web" / "static" / "style.css"
THEMES = REPO / "themes"

# Every theme file shipped in the repo, checked as a set so adding one cannot
# quietly skip the checks below.
SHIPPED = ("template.css", "light.css")


@pytest.fixture(autouse=True)
def clean_css():
    """No test may inherit a stylesheet or shader from the one before it."""
    for path in (theming.css_path(), theming.shader_path()):
        path.unlink(missing_ok=True)
    yield
    for path in (theming.css_path(), theming.shader_path()):
        path.unlink(missing_ok=True)


@pytest.fixture
def admin():
    return db.create_user("root", "hunter2hunter2", role="admin")


@pytest.fixture
def plain_user(admin):
    return db.create_user("bob", "hunter2hunter2")


def tokens_in(text):
    """Variable names declared in the first :root block of a stylesheet."""
    start = text.index(":root")
    block = text[start : text.index("\n}", start)]
    return set(re.findall(r"^\s+(--[a-z0-9-]+)\s*:", block, re.MULTILINE))


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------
def test_empty_css_stays_empty():
    assert theming.normalise("") == ""
    assert theming.normalise("   \n\n  ") == ""


def test_plain_css_is_left_alone():
    assert theming.normalise(".card { color: red; }") == ".card { color: red; }\n"


def test_import_below_a_rule_is_hoisted():
    """CSS ignores @import after any other rule, so it has to move up."""
    result = theming.normalise(
        ".card { color: red; }\n@import url('https://example.com/t.css');"
    )
    assert result.startswith("@import url('https://example.com/t.css');")
    assert ".card { color: red; }" in result


def test_import_already_on_top_keeps_working():
    result = theming.normalise("@import url('https://x/t.css');\n.card { color: red; }")
    assert result.index("@import") < result.index(".card")


def test_several_imports_keep_their_order():
    result = theming.normalise(
        ".a {}\n@import url('https://x/one.css');\n@import url('https://x/two.css');"
    )
    assert result.index("one.css") < result.index("two.css")


def test_duplicate_imports_are_collapsed():
    result = theming.normalise(
        "@import url('https://x/t.css');\n.a {}\n@import url('https://x/t.css');"
    )
    assert result.count("@import") == 1


def test_import_only_theme_needs_no_trailing_body():
    assert theming.normalise("@import url('https://x/t.css');") == (
        "@import url('https://x/t.css');\n"
    )


def test_indented_import_is_still_found():
    result = theming.normalise(".a {}\n    @import url('https://x/t.css');")
    assert result.startswith("@import")


def test_media_qualified_import_survives():
    result = theming.normalise(".a {}\n@import url('https://x/t.css') screen;")
    assert result.startswith("@import url('https://x/t.css') screen;")


def test_windows_line_endings_are_normalised():
    assert "\r" not in theming.normalise(".a {\r\n  color: red;\r\n}")


def test_an_import_inside_a_rule_is_not_hoisted():
    """Only whole lines are moved, so a false positive mid rule stays put."""
    css = ".a {\n  content: '@import url(x);';\n}"
    assert theming.normalise(css).startswith(".a {")


# ---------------------------------------------------------------------------
# Imports a browser will silently refuse
#
# A stylesheet has to arrive as text/css. Hosts that send text/plain get the
# import dropped with nothing in the console, so this is the only warning
# anybody gets.
# ---------------------------------------------------------------------------
def test_a_normal_import_is_not_flagged():
    assert (
        theming.import_warnings("@import url('https://cdn.jsdelivr.net/x.css');") == []
    )


def test_css_without_imports_is_not_flagged():
    assert theming.import_warnings(".card { color: red; }") == []


def test_pastebin_is_flagged():
    found = theming.import_warnings("@import url('https://pastebin.com/raw/abc');")
    assert len(found) == 1
    assert found[0]["host"] == "pastebin.com"


def test_github_raw_is_flagged():
    found = theming.import_warnings(
        "@import url('https://raw.githubusercontent.com/u/r/main/t.css');"
    )
    assert found[0]["host"] == "raw.githubusercontent.com"


def test_gist_raw_is_flagged():
    found = theming.import_warnings(
        "@import url('https://gist.githubusercontent.com/u/1/raw/t.css');"
    )
    assert found[0]["host"] == "gist.githubusercontent.com"


def test_github_raw_gets_a_working_replacement():
    """The fix is a host swap plus an @ before the branch, so just offer it."""
    found = theming.import_warnings(
        "@import url('https://raw.githubusercontent.com/me/theme/main/dark.css');"
    )
    assert found[0]["suggestion"] == (
        "https://cdn.jsdelivr.net/gh/me/theme@main/dark.css"
    )


def test_a_nested_path_survives_the_rewrite():
    found = theming.import_warnings(
        "@import url('https://raw.githubusercontent.com/me/r/v2/themes/a/b.css');"
    )
    assert found[0]["suggestion"].endswith("/gh/me/r@v2/themes/a/b.css")


def test_pastebin_has_no_replacement_to_offer():
    found = theming.import_warnings("@import url('https://pastebin.com/raw/abc');")
    assert found[0]["suggestion"] is None


def test_every_bad_import_is_reported():
    found = theming.import_warnings(
        "@import url('https://pastebin.com/raw/a');\n"
        "@import url('https://raw.githubusercontent.com/u/r/main/t.css');\n"
        "@import url('https://cdn.jsdelivr.net/gh/u/r@main/t.css');"
    )
    assert len(found) == 2


def test_a_bare_import_without_url_is_still_read():
    found = theming.import_warnings('@import "https://pastebin.com/raw/abc";')
    assert found[0]["host"] == "pastebin.com"


def test_the_host_match_ignores_case():
    found = theming.import_warnings("@import url('https://PasteBin.com/raw/abc');")
    assert found[0]["host"] == "pastebin.com"


def test_a_lookalike_host_is_not_flagged():
    """Matching on the hostname, not a substring, so this must stay quiet."""
    assert (
        theming.import_warnings("@import url('https://pastebin.com.evil.test/x');")
        == []
    )


def test_the_api_warns_when_saving_a_bad_import(client):
    payload = client.put(
        "/api/custom-css", json={"css": "@import url('https://pastebin.com/raw/abc');"}
    ).get_json()
    assert payload["warnings"][0]["host"] == "pastebin.com"


def test_the_api_warns_about_an_already_stored_import(client):
    """So an existing broken theme is flagged when the page opens, not only on save."""
    theming.write("@import url('https://raw.githubusercontent.com/u/r/main/t.css');")
    payload = client.get("/api/custom-css").get_json()
    assert payload["warnings"][0]["suggestion"].startswith("https://cdn.jsdelivr.net/")


def test_a_good_theme_reports_no_warnings(client):
    payload = client.put("/api/custom-css", json={"css": ".card {}"}).get_json()
    assert payload["warnings"] == []


def test_a_bad_import_is_still_saved(client):
    """It is a warning, not a rejection. The URL might be fine tomorrow."""
    client.put(
        "/api/custom-css", json={"css": "@import url('https://pastebin.com/raw/a');"}
    )
    assert "pastebin.com" in theming.read()


def test_the_shipped_themes_do_not_recommend_a_dead_host():
    """The docs pointed at GitHub raw once, and it silently never worked."""
    for name in SHIPPED:
        text = (THEMES / name).read_text()
        for host in theming.PLAIN_TEXT_HOSTS:
            assert host not in text, f"themes/{name} still suggests {host}"


def test_the_readme_does_not_recommend_a_dead_host():
    readme = (REPO / "README.md").read_text()
    theming_section = readme[readme.index("## Theming") : readme.index("## Optional")]
    for host in theming.PLAIN_TEXT_HOSTS:
        # named as things to avoid is fine, offered inside an @import is not
        assert f"@import url('https://{host}" not in theming_section


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def test_read_with_nothing_stored():
    assert theming.read() == ""


def test_write_then_read_round_trips():
    theming.write(".card { color: red; }")
    assert ".card { color: red; }" in theming.read()


def test_write_returns_what_it_stored():
    stored = theming.write(".a {}\n@import url('https://x/t.css');")
    assert stored == theming.read()


def test_clearing_removes_the_file():
    theming.write(".card {}")
    assert theming.css_path().exists()
    theming.write("")
    assert not theming.css_path().exists()


def test_clearing_when_nothing_is_stored_is_fine():
    assert theming.write("") == ""


def test_oversize_css_is_refused():
    with pytest.raises(theming.CSSTooLarge):
        theming.write("a" * (theming.MAX_BYTES + 1))


def test_a_refused_write_leaves_the_old_theme_alone():
    theming.write(".keep { color: red; }")
    with pytest.raises(theming.CSSTooLarge):
        theming.write("a" * (theming.MAX_BYTES + 1))
    assert ".keep" in theming.read()


def test_size_is_measured_in_bytes_not_characters():
    """A multibyte character must count for what it really costs."""
    with pytest.raises(theming.CSSTooLarge):
        theming.write("ü" * theming.MAX_BYTES)


def test_write_leaves_no_temp_files_behind():
    theming.write(".card {}")
    leftovers = list(theming.css_path().parent.glob("*.tmp"))
    assert leftovers == []


def test_unicode_survives_a_round_trip():
    theming.write('.a::after { content: "★ Übergrösse"; }')
    assert "★ Übergrösse" in theming.read()


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
def test_version_is_empty_without_a_theme():
    assert theming.version() == ""


def test_version_changes_with_the_content():
    theming.write(".a { color: red; }")
    first = theming.version()
    theming.write(".a { color: blue; }")
    assert theming.version() != first


def test_version_is_stable_for_the_same_content():
    theming.write(".a { color: red; }")
    assert theming.version() == theming.version()


# ---------------------------------------------------------------------------
# The served stylesheet
# ---------------------------------------------------------------------------
def test_custom_css_is_served_as_a_stylesheet(client):
    theming.write(".card { color: red; }")
    response = client.get("/custom.css")
    assert response.status_code == 200
    assert response.mimetype == "text/css"
    assert b".card { color: red; }" in response.data


def test_custom_css_is_empty_but_present_without_a_theme(client):
    response = client.get("/custom.css")
    assert response.status_code == 200
    assert response.data == b""


def test_a_stored_theme_may_be_cached_hard(client):
    theming.write(".card {}")
    assert "immutable" in client.get("/custom.css").headers["Cache-Control"]


def test_an_empty_theme_is_never_cached(client):
    assert "no-store" in client.get("/custom.css").headers["Cache-Control"]


# ---------------------------------------------------------------------------
# Where the link appears
# ---------------------------------------------------------------------------
def test_pages_link_the_theme_once_it_exists(client):
    theming.write(".card {}")
    assert b"data-custom-css" in client.get("/").data


def test_pages_do_not_link_an_empty_theme(client):
    assert b"data-custom-css" not in client.get("/").data


def test_the_link_carries_the_content_hash(client):
    theming.write(".card {}")
    assert theming.version().encode() in client.get("/").data


def test_nocss_leaves_the_theme_out(client):
    theming.write(".card {}")
    assert b"data-custom-css" not in client.get("/?nocss=1").data


def test_nocss_works_on_the_settings_page_too(client):
    """The one page you need back when a theme hides everything."""
    theming.write(".card { display: none; }")
    assert b"data-custom-css" not in client.get("/settings?nocss=1").data
    assert b"data-custom-css" in client.get("/settings").data


def test_any_other_nocss_value_keeps_the_theme(client):
    theming.write(".card {}")
    assert b"data-custom-css" in client.get("/?nocss=0").data


def test_the_login_page_is_never_themed(auth_client):
    """A theme must not be able to restyle the form people type a password into."""
    theming.write(".card {}")
    assert b"data-custom-css" not in auth_client.get("/login").data


def test_the_setup_page_is_never_themed(auth_client):
    theming.write(".card {}")
    assert b"data-custom-css" not in auth_client.get("/setup").data


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_get_returns_the_stored_css(client):
    theming.write(".card { color: red; }")
    payload = client.get("/api/custom-css").get_json()
    assert ".card { color: red; }" in payload["css"]
    assert payload["max_bytes"] == theming.MAX_BYTES


def test_put_stores_the_css(client):
    response = client.put("/api/custom-css", json={"css": ".card { color: red; }"})
    assert response.status_code == 200
    assert ".card { color: red; }" in theming.read()


def test_put_returns_the_new_version(client):
    payload = client.put("/api/custom-css", json={"css": ".card {}"}).get_json()
    assert payload["version"] == theming.version()


def test_put_returns_the_hoisted_css(client):
    """The box shows back what was stored, not what was typed."""
    payload = client.put(
        "/api/custom-css", json={"css": ".a {}\n@import url('https://x/t.css');"}
    ).get_json()
    assert payload["css"].startswith("@import")


def test_put_can_clear_the_theme(client):
    theming.write(".card {}")
    client.put("/api/custom-css", json={"css": ""})
    assert theming.read() == ""


def test_put_rejects_a_non_string(client):
    assert client.put("/api/custom-css", json={"css": 42}).status_code == 400


def test_put_without_a_css_key_clears_nothing_new(client):
    assert client.put("/api/custom-css", json={}).status_code == 200


def test_put_refuses_an_oversized_theme(client):
    response = client.put(
        "/api/custom-css", json={"css": "a" * (theming.MAX_BYTES + 1)}
    )
    assert response.status_code == 413


def test_custom_css_is_admin_only(auth_app, auth_client):
    """A plain user may load the theme but never change it."""
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.get_custom_css" in ADMIN_ENDPOINTS
    assert "api.update_custom_css" in ADMIN_ENDPOINTS
    assert "pages.custom_css" not in ADMIN_ENDPOINTS


def test_anonymous_cannot_read_the_settings_api(auth_client, admin):
    assert auth_client.get("/api/custom-css").status_code == 401


def test_anonymous_cannot_write_a_theme(auth_client, admin):
    assert auth_client.put("/api/custom-css", json={"css": ".a {}"}).status_code == 401


def test_a_plain_user_cannot_change_the_theme(auth_client, plain_user):
    auth_client.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    response = auth_client.put("/api/custom-css", json={"css": ".a {}"})
    assert response.status_code == 403


def test_a_plain_user_can_still_load_the_theme(auth_client, plain_user):
    """Everyone has to be able to fetch it, or the page renders unstyled."""
    theming.write(".card { color: red; }")
    auth_client.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    assert b".card { color: red; }" in auth_client.get("/custom.css").data


# ---------------------------------------------------------------------------
# The shipped themes stay in step with the stylesheet
# ---------------------------------------------------------------------------
def test_template_documents_every_token():
    """A token added to style.css has to be written up, or themes miss it."""
    missing = tokens_in(STYLE.read_text()) - tokens_in(
        (THEMES / "template.css").read_text()
    )
    assert not missing, f"themes/template.css is missing: {sorted(missing)}"


def test_template_invents_no_tokens():
    extra = tokens_in((THEMES / "template.css").read_text()) - tokens_in(
        STYLE.read_text()
    )
    assert not extra, (
        f"themes/template.css documents tokens that do not exist: {sorted(extra)}"
    )


def test_the_light_theme_only_sets_real_tokens():
    """Catches a typo in the example theme before someone copies it."""
    unknown = tokens_in((THEMES / "light.css").read_text()) - tokens_in(
        STYLE.read_text()
    )
    assert not unknown, f"themes/light.css sets unknown tokens: {sorted(unknown)}"


def test_the_light_theme_repaints_the_backgrounds():
    """A light theme that forgets a surface looks broken, so check the big ones."""
    light = tokens_in((THEMES / "light.css").read_text())
    for token in ("--bg", "--surface", "--surface-modal", "--surface-input", "--text"):
        assert token in light, f"themes/light.css never sets {token}"


def test_the_light_theme_flips_the_colour_scheme():
    """Without this the native checkboxes and dropdowns stay dark."""
    assert "--color-scheme: light" in (THEMES / "light.css").read_text()


def test_the_shipped_themes_are_valid_enough_to_store():
    """They go through the same normalising as anything pasted into the box."""
    for name in SHIPPED:
        stored = theming.write((THEMES / name).read_text())
        assert stored.strip(), f"{name} normalised away to nothing"


def test_the_stylesheet_has_no_stray_colours():
    """Every colour belongs to a token, or a theme cannot reach it."""
    text = STYLE.read_text()
    end = text.index("\n}", text.index(":root {"))
    offenders = [
        line.strip()
        for line in text[end:].splitlines()
        if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", line)
    ]
    assert not offenders, f"hardcoded colours outside :root: {offenders[:5]}"


# ---------------------------------------------------------------------------
# Theme surfaces
#
# Layers and body state exist so a theme does not have to hijack a pseudo
# element or guess at internal class names.
# ---------------------------------------------------------------------------
def test_every_page_offers_two_paint_layers(client):
    for path in ("/", "/library", "/settings"):
        assert client.get(path).data.count(b'class="theme-layer"') == 2, path


def test_body_names_the_page(client):
    assert b'data-page="index"' in client.get("/").data
    assert b'data-page="settings"' in client.get("/settings").data
    assert b'data-page="library"' in client.get("/library").data


def test_body_starts_with_neutral_state(client):
    body = client.get("/").data
    assert b'data-queue="idle"' in body
    assert b'data-modal="closed"' in body


def test_the_layers_are_not_on_the_login_page(auth_client):
    """The sign-in page stays outside the theming surface entirely."""
    assert b'class="theme-layer"' not in auth_client.get("/login").data


# ---------------------------------------------------------------------------
# Fragment shader
# ---------------------------------------------------------------------------
def test_no_shader_stored_by_default():
    assert theming.read_shader() == ""
    assert theming.shader_version() == ""


def test_shader_round_trips():
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    assert "fragColor" in theming.read_shader()


def test_shader_version_tracks_the_source():
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    first = theming.shader_version()
    theming.write_shader("void main() { fragColor = vec4(0.5); }")
    assert theming.shader_version() != first


def test_clearing_the_shader_removes_the_file():
    theming.write_shader("void main() {}")
    assert theming.shader_path().exists()
    theming.write_shader("")
    assert not theming.shader_path().exists()


def test_an_oversized_shader_is_refused():
    with pytest.raises(theming.ShaderTooLarge):
        theming.write_shader("a" * (theming.MAX_SHADER_BYTES + 1))


def test_a_refused_shader_leaves_the_old_one_alone():
    theming.write_shader("void main() { /* keep */ }")
    with pytest.raises(theming.ShaderTooLarge):
        theming.write_shader("a" * (theming.MAX_SHADER_BYTES + 1))
    assert "keep" in theming.read_shader()


def test_shader_writes_leave_no_temp_files():
    theming.write_shader("void main() {}")
    assert list(theming.shader_path().parent.glob("*.tmp")) == []


def test_the_shader_is_served_as_plain_text(client):
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    response = client.get("/custom.frag")
    assert response.status_code == 200
    assert b"fragColor" in response.data


def test_a_stored_shader_may_be_cached_hard(client):
    theming.write_shader("void main() {}")
    assert "immutable" in client.get("/custom.frag").headers["Cache-Control"]


def test_pages_add_the_canvas_once_a_shader_exists(client):
    assert b'id="themeShader"' not in client.get("/").data
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    assert b'id="themeShader"' in client.get("/").data


def test_the_canvas_carries_the_shader_version(client):
    theming.write_shader("void main() {}")
    assert theming.shader_version().encode() in client.get("/").data


def test_nocss_skips_the_shader_too(client):
    """The same escape hatch has to cover a shader that hides the page."""
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    assert b'id="themeShader"' not in client.get("/?nocss=1").data
    assert b'id="themeShader"' not in client.get("/settings?nocss=1").data


def test_the_login_page_never_runs_a_shader(auth_client):
    theming.write_shader("void main() {}")
    assert b'id="themeShader"' not in auth_client.get("/login").data


def test_the_setup_page_never_runs_a_shader(auth_client):
    theming.write_shader("void main() {}")
    assert b'id="themeShader"' not in auth_client.get("/setup").data


def test_the_api_returns_the_shader(client):
    theming.write_shader("void main() { fragColor = vec4(1.0); }")
    payload = client.get("/api/custom-shader").get_json()
    assert "fragColor" in payload["shader"]
    assert payload["max_bytes"] == theming.MAX_SHADER_BYTES


def test_the_api_stores_a_shader(client):
    response = client.put(
        "/api/custom-shader", json={"shader": "void main() { fragColor = vec4(1.0); }"}
    )
    assert response.status_code == 200
    assert "fragColor" in theming.read_shader()


def test_the_api_rejects_a_non_string_shader(client):
    assert client.put("/api/custom-shader", json={"shader": 7}).status_code == 400


def test_the_api_refuses_an_oversized_shader(client):
    response = client.put(
        "/api/custom-shader", json={"shader": "a" * (theming.MAX_SHADER_BYTES + 1)}
    )
    assert response.status_code == 413


def test_the_shader_is_admin_only():
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.get_custom_shader" in ADMIN_ENDPOINTS
    assert "api.update_custom_shader" in ADMIN_ENDPOINTS
    # everyone has to be able to fetch it or the page renders without it
    assert "pages.custom_shader" not in ADMIN_ENDPOINTS


def test_a_plain_user_cannot_change_the_shader(auth_client, plain_user):
    auth_client.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    response = auth_client.put("/api/custom-shader", json={"shader": "void main() {}"})
    assert response.status_code == 403


def test_the_shader_field_never_accepts_script(client):
    """It is stored verbatim and only ever served as text, never executed."""
    client.put("/api/custom-shader", json={"shader": "<script>alert(1)</script>"})
    served = client.get("/custom.frag")
    assert served.mimetype == "text/plain"
    assert b"<script>" in served.data
