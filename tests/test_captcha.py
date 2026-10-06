"""CAPTCHA interactions, URL capture and cleanup without live provider traffic."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest
from patchright.sync_api import Error

from aniworld import autodeps
from aniworld.playwright import captcha

SOURCE = "https://s.to/serie/example/staffel-1/episode-1"
PLAYER = "https://rotating-provider.example/e/video"


@pytest.fixture
def browser(monkeypatch):
    from patchright import sync_api

    page = Mock(url=SOURCE, frames=[])
    context = Mock(pages=[page])
    context.new_page.return_value = page
    context.cookies.return_value = []
    handle = SimpleNamespace(context=context, close=Mock())
    monkeypatch.setattr(sync_api, "sync_playwright", MagicMock())
    monkeypatch.setattr(autodeps, "ensure_patchright_chromium", Mock())
    monkeypatch.setattr(autodeps, "_ensure_xvfb", Mock())
    monkeypatch.setattr(captcha, "_launch_browser_context", Mock(return_value=handle))
    monkeypatch.setattr(captcha, "_sync_session_user_agent", Mock())
    monkeypatch.setattr(captcha._local, "queue_id", None, raising=False)
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(captcha.time, "monotonic", lambda: clock.now)

    def wait(milliseconds):
        clock.now += milliseconds / 1000

    page.wait_for_timeout.side_effect = wait
    return handle, page


def test_browser_prepares_chromium_and_display_before_launch(browser, monkeypatch):
    from patchright import sync_api

    handle, page = browser
    events = []
    runtime = sync_api.sync_playwright()
    monkeypatch.setattr(
        autodeps, "ensure_patchright_chromium", lambda: events.append("chromium")
    )
    monkeypatch.setattr(autodeps, "_ensure_xvfb", lambda: events.append("display"))

    def start():
        events.append("runtime")
        return runtime

    def launch(*args, **kwargs):
        events.append("launch")
        return handle

    monkeypatch.setattr(sync_api, "sync_playwright", start)
    monkeypatch.setattr(captcha, "_launch_browser_context", launch)
    with captcha._browser(SOURCE) as result:
        assert result == (handle.context, page)
    assert events == ["chromium", "display", "runtime", "launch"]
    handle.close.assert_called_once_with()


@pytest.mark.parametrize(
    "marker", ["cf-turnstile", "hcaptcha.com", "g-recaptcha", "altcha-widget"]
)
def test_html_detection_supports_existing_widgets(marker):
    assert captcha.is_captcha_page(f"<div>{marker}</div>")
    assert not captcha.is_captcha_page("<html>ordinary page</html>")


@pytest.mark.parametrize("status", [403, 503])
def test_blocked_responses_use_the_browser(status):
    assert captcha.is_captcha_page("", status)


def test_dom_detection_keeps_solved_widget_until_form_is_submitted():
    page = Mock()
    page.evaluate.return_value = False
    frame = Mock()
    frame.child_frames = []
    frame.evaluate.return_value = [{"kind": "hcaptcha", "ready": True}]
    page.frames = [frame]
    assert captcha._is_captcha_page_dom(page)
    frame.evaluate.return_value = []
    assert not captcha._is_captcha_page_dom(page)


def test_navigation_during_detection_keeps_waiting():
    page = Mock()
    page.evaluate.side_effect = Error("execution context destroyed")
    assert captcha._is_captcha_page_dom(page)


@pytest.mark.parametrize(
    "kind,source",
    [
        ("turnstile", "https://challenges.cloudflare.com/widget"),
        ("hcaptcha", "https://newassets.hcaptcha.com/widget"),
        ("recaptcha", "https://www.google.com/recaptcha/api2/anchor"),
    ],
)
def test_stacked_widgets_wait_for_every_token_and_do_not_repeat_clicks(
    kind, source, monkeypatch
):
    offset = Mock(side_effect=[-3, 3])
    monkeypatch.setattr(captcha.random, "randint", offset)
    page = Mock()
    owner = Mock()
    child = Mock(url=source)
    child.is_detached.return_value = False
    child.frame_element.return_value.bounding_box.return_value = {
        "x": 100,
        "y": 200,
        "width": 300,
        "height": 70,
    }
    owner.child_frames = [child]
    owner.evaluate.return_value = [
        {"kind": kind, "ready": False},
        {"kind": "altcha", "ready": True},
    ]
    page.frames = [owner]
    solver = captcha._ChallengeSolver()
    assert not solver.ready_to_submit(page)
    assert not solver.ready_to_submit(page)
    page.mouse.click.assert_called_once_with(125, 238)
    assert offset.call_args_list == [call(-3, 3), call(-3, 3)]
    owner.evaluate.return_value = [
        {"kind": kind, "ready": True},
        {"kind": "altcha", "ready": True},
    ]
    assert solver.ready_to_submit(page)
    assert not captcha._ChallengeSolver().ready_to_submit(Mock(frames=[]))


def test_image_challenge_is_left_for_user():
    page = Mock()
    owner = Mock()
    owner.evaluate.return_value = [{"kind": "hcaptcha", "ready": False}]
    child = Mock(url="https://hcaptcha.com/challenge")
    child.is_detached.return_value = False
    child.frame_element.return_value.bounding_box.return_value = {
        "x": 0,
        "y": 0,
        "width": 400,
        "height": 500,
    }
    owner.child_frames = [child]
    page.frames = [owner]
    assert not captcha._ChallengeSolver().ready_to_submit(page)
    page.mouse.click.assert_not_called()


def test_widget_click_retries_after_interception(monkeypatch):
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(captcha.time, "monotonic", lambda: clock.now)
    child = Mock(url="https://challenges.cloudflare.com/widget")
    child.is_detached.return_value = False
    child.frame_element.return_value.bounding_box.return_value = {
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 70,
    }
    frame = Mock(child_frames=[child])
    frame.evaluate.return_value = [{"kind": "turnstile", "ready": False}]
    page = Mock(frames=[frame])
    solver = captcha._ChallengeSolver()
    assert not solver.ready_to_submit(page)
    clock.now += 1
    assert not solver.ready_to_submit(page)
    page.mouse.click.assert_called_once()
    clock.now += 4
    assert not solver.ready_to_submit(page)
    assert page.mouse.click.call_count == 2


def test_detached_widget_cannot_make_other_solved_widgets_ready():
    ready = Mock()
    ready.child_frames = []
    ready.evaluate.return_value = [{"kind": "turnstile", "ready": True}]
    detached = Mock()
    detached.evaluate.side_effect = Error("frame detached")
    page = Mock(frames=[ready, detached])
    assert not captcha._ChallengeSolver().ready_to_submit(page)


@pytest.mark.parametrize("outcome", ["solved", "timeout", "navigation-error"])
def test_interactive_solve_delivers_clicks_and_always_cleans_up(
    browser, monkeypatch, outcome
):
    handle, page = browser
    started, ended = Mock(), Mock()
    monkeypatch.setattr(captcha._local, "queue_id", 42)
    monkeypatch.setattr(captcha, "_on_captcha_start", started)
    monkeypatch.setattr(captcha, "_on_captcha_end", ended)
    monkeypatch.setattr(
        captcha, "_is_captcha_page_dom", lambda page: outcome != "solved"
    )
    solver = Mock()
    solver.ready_to_submit.return_value = False
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)
    sessions = []

    def navigate(*args, **kwargs):
        assert captcha.get_captcha_status()["url"] == SOURCE
        session = captcha._active_sessions[42]
        sessions.append(session)
        session.enqueue_click(120, 80)
        if outcome == "navigation-error":
            raise Error("navigation failed")

    page.goto.side_effect = navigate
    page.screenshot.return_value = b"jpeg"
    if outcome == "navigation-error":
        with pytest.raises(Error, match="navigation failed"):
            captcha._solve(SOURCE, timeout=1)
    else:
        assert captcha._solve(SOURCE, timeout=1) == (
            SOURCE if outcome == "solved" else None
        )
        page.mouse.click.assert_called_once_with(120, 80)
        assert sessions[0].get_screenshot() == b"jpeg"
    assert sessions[0].done
    assert sessions[0].result_url == (SOURCE if outcome == "solved" else None)
    assert captcha.get_captcha_status() is None
    assert 42 not in captcha._active_sessions
    started.assert_called_once_with(42, SOURCE)
    ended.assert_called_once_with(42)
    handle.close.assert_called_once()


@pytest.mark.parametrize("destination", ["iframe", "popup"])
@pytest.mark.parametrize("manual", ["0", "1"])
def test_sto_clicks_continue_without_touching_widgets(
    browser, monkeypatch, destination, manual
):
    handle, page = browser
    monkeypatch.setenv("ANIWORLD_CAPTCHA_MANUAL", manual)
    frame = Mock(url="about:blank")
    frame.name = "player-iframe"
    page.frames = [frame]
    button = Mock()
    frame.locator.return_value.all.return_value = [button]
    solver = Mock()
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)
    monkeypatch.setattr(
        captcha,
        "_is_captcha_page_dom",
        Mock(side_effect=AssertionError("S.to must skip widgets")),
    )
    ad = Mock(url="https://ads.example/")

    def prepare(*args):
        handle.context.on.call_args.args[1](ad)
        return True

    page.evaluate.side_effect = prepare

    def submit(*args):
        if destination == "iframe":
            frame.url = PLAYER
        else:
            popup = Mock(url=PLAYER, frames=[])
            handle.context.on.call_args.args[1](popup)
            popup.close.assert_not_called()
            handle.context.pages.append(popup)

    button.evaluate.side_effect = submit
    assert (
        captcha.solve_sto_modal(SOURCE, "VOE", "Deutsch", "https://s.to/r?t=token")
        == PLAYER
    )
    ad.close.assert_called_once()
    solver.ready_to_submit.assert_not_called()
    button.evaluate.assert_called_once()
    handle.close.assert_called_once()


@pytest.mark.parametrize("manual", ["0", "1"])
def test_sto_solves_required_widgets_after_initial_submission(
    browser, monkeypatch, manual
):
    handle, page = browser
    monkeypatch.setenv("ANIWORLD_CAPTCHA_MANUAL", manual)
    page.evaluate.return_value = True
    solver = Mock()
    ad = Mock(url="https://ads.example/")

    def wait_for_widgets(page):
        if solver.ready_to_submit.call_count == 1:
            handle.context.on.call_args.args[1](ad)
            return False
        return True

    solver.ready_to_submit.side_effect = wait_for_widgets
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)
    submissions = []

    def submit(page):
        submissions.append(page.url)
        if len(submissions) == 2:
            page.url = PLAYER
        return True

    monkeypatch.setattr(captcha, "_click_submit_button", submit)
    assert captcha.solve_sto_modal(SOURCE, "VOE", "Deutsch") == PLAYER
    assert len(submissions) == 2
    assert solver.ready_to_submit.call_count == 2
    ad.close.assert_called_once()
    handle.close.assert_called_once()


@pytest.mark.parametrize(
    "visible,offscreen,hidden",
    [
        ("auto", False, False),
        ("auto", True, True),
        ("1", True, False),
        ("0", False, True),
        ("invalid", True, True),
        (" AUTO ", False, False),
    ],
)
def test_window_visibility_keeps_chromium_headed(
    tmp_path, monkeypatch, visible, offscreen, hidden
):
    executable = tmp_path / "chromium"
    executable.touch()
    runtime = Mock()
    runtime.chromium.executable_path = str(executable)
    monkeypatch.setenv("ANIWORLD_CAPTCHA_VISIBLE", visible)
    handle = captcha._launch_browser_context(runtime, offscreen=offscreen)
    options = runtime.chromium.launch.call_args.kwargs
    assert options["headless"] is False
    assert ("--window-position=-32000,-32000" in options["args"]) == hidden
    assert not any(arg.startswith("--window-size") for arg in options["args"])
    runtime.chromium.launch.return_value.new_context.assert_called_once_with(
        no_viewport=True
    )
    handle.close()
    runtime.chromium.launch.return_value.close.assert_called_once()


def test_manual_mode_waits_for_user_tokens_without_interacting(monkeypatch):
    monkeypatch.setenv("ANIWORLD_CAPTCHA_MANUAL", "1")
    owner = Mock(child_frames=[])
    kinds = ["turnstile", "hcaptcha", "recaptcha", "checkbox", "altcha"]
    owner.evaluate.side_effect = [
        [{"kind": kind, "ready": False} for kind in kinds],
        [{"kind": kind, "ready": True} for kind in kinds],
    ]
    page = Mock(frames=[owner])
    solver = captcha._ChallengeSolver()
    assert not solver.ready_to_submit(page)
    assert solver.ready_to_submit(page)
    page.mouse.click.assert_not_called()
    owner.get_by_role.assert_not_called()
    assert owner.evaluate.call_count == 2


@pytest.mark.parametrize(
    "configured,waits", [("2", 4), ("invalid", 2), ("0", 2), ("-1", 2), ("", 2)]
)
def test_solve_timeout_override_and_invalid_fallback(
    browser, monkeypatch, configured, waits
):
    handle, page = browser
    monkeypatch.setenv("ANIWORLD_CAPTCHA_TIMEOUT", configured)
    monkeypatch.setattr(captcha, "_is_captcha_page_dom", lambda page: True)
    solver = Mock()
    solver.ready_to_submit.return_value = False
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)
    assert captcha._solve(SOURCE, timeout=1) is None
    assert page.wait_for_timeout.call_count == waits
    handle.close.assert_called_once()


def test_hanime_timeout_uses_override_and_releases_browser(browser, monkeypatch):
    handle, page = browser
    monkeypatch.setenv("ANIWORLD_CAPTCHA_TIMEOUT", "1")
    monkeypatch.setattr(captcha, "_is_captcha_page_dom", lambda page: False)
    with pytest.raises(TimeoutError, match="after 1s"):
        captcha.playwright_get_hanime_manifest_token(SOURCE)
    assert page.wait_for_timeout.call_count == 2
    assert captcha.get_captcha_status() is None
    handle.close.assert_called_once()


@pytest.mark.parametrize("enabled", ["0", "1"])
def test_debug_logs_browser_errors_and_ignores_ordinary_console_messages(
    monkeypatch, enabled
):
    monkeypatch.setenv("ANIWORLD_CAPTCHA_DEBUG_LOG", enabled)
    log = Mock()
    monkeypatch.setattr(captcha, "logger", log)
    page = Mock()
    captcha._attach_debug_listeners(page)
    if enabled == "0":
        page.on.assert_not_called()
        page.context.new_cdp_session.assert_not_called()
        return
    debug = page.context.new_cdp_session.return_value
    debug.send.assert_called_once_with("Runtime.enable")
    callbacks = {call.args[0]: call.args[1] for call in debug.on.call_args_list}
    for kind in ("log", "debug", "info"):
        callbacks["Runtime.consoleAPICalled"](
            {"type": kind, "args": [{"value": "ordinary message"}]}
        )
    log.warning.assert_not_called()
    for kind in ("error", "warning"):
        callbacks["Runtime.consoleAPICalled"](
            {"type": kind, "args": [{"value": "browser message"}]}
        )
        log.warning.assert_called_with(
            "CAPTCHA browser %s: %s", kind, "browser message"
        )
    callbacks["Runtime.exceptionThrown"](
        {
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "script failed"},
            }
        }
    )
    log.warning.assert_called_with("CAPTCHA page error: %s", "script failed")
    callbacks["Runtime.exceptionThrown"](
        {"exceptionDetails": {"text": "Uncaught error"}}
    )
    log.warning.assert_called_with("CAPTCHA page error: %s", "Uncaught error")
    callbacks = {call.args[0]: call.args[1] for call in page.on.call_args_list}
    callbacks["requestfailed"](SimpleNamespace(url=SOURCE, failure="net::ERR_FAILED"))
    log.warning.assert_called_with(
        "CAPTCHA request failed: %s (%s)", SOURCE, "net::ERR_FAILED"
    )


def test_debug_listener_setup_does_not_break_hanime_token_capture(browser, monkeypatch):
    handle, page = browser
    monkeypatch.setenv("ANIWORLD_CAPTCHA_DEBUG_LOG", "1")

    def navigate(*args, **kwargs):
        callbacks = {call.args[0]: call.args[1] for call in page.on.call_args_list}
        page.context.new_cdp_session.return_value.send.assert_called_once_with(
            "Runtime.enable"
        )
        callbacks["response"](
            SimpleNamespace(
                status=200,
                url="https://auth.hanime.tv/",
                header_value=lambda name: "token",
            )
        )

    page.goto.side_effect = navigate
    assert captcha.playwright_get_hanime_manifest_token(SOURCE) == "token"
    handle.close.assert_called_once()


def test_provider_capture_rejects_challenges_and_existing_ad_frames():
    frames = []
    for url in (
        "https://ads.example/banner",
        "https://newassets.hcaptcha.com/widget",
        "https://challenges.cloudflare.com/widget",
        "https://www.google.com/recaptcha/api2/anchor",
        "https://s.to/r?t=token",
    ):
        frame = Mock(url=url)
        frame.name = ""
        frames.append(frame)
    page = Mock(url=SOURCE, frames=frames)
    context = Mock(pages=[page])
    assert captcha._provider_result(context, SOURCE, False, set()) is None
    assert captcha._provider_result(context, SOURCE, True, {frames[0].url}) is None
    player = Mock(url=PLAYER)
    player.name = "player-iframe"
    frames.append(player)
    assert captcha._provider_result(context, SOURCE, False, set()) == PLAYER
    assert captcha._extract_iframe_url(page, SOURCE) == PLAYER


def test_browser_closes_when_context_creation_fails(tmp_path):
    executable = tmp_path / "chromium"
    executable.touch()
    runtime = Mock()
    runtime.chromium.executable_path = str(executable)
    browser = runtime.chromium.launch.return_value
    browser.new_context.side_effect = Error("context failed")
    with pytest.raises(Error, match="context failed"):
        captcha._launch_browser_context(runtime)
    browser.close.assert_called_once()


def test_failed_handshake_does_not_leave_queue_session_active(browser, monkeypatch):
    handle, page = browser
    monkeypatch.setattr(captcha._local, "queue_id", 42)
    page.goto.side_effect = Error("navigation failed")
    with pytest.raises(Error, match="navigation failed"):
        captcha.playwright_get_hanime_manifest_token(SOURCE)
    assert captcha.get_captcha_status() is None
    assert 42 not in captcha._active_sessions
    handle.close.assert_called_once()


def test_navigation_ignores_old_child_frames():
    owner = Mock()
    owner.evaluate.return_value = []
    detached = Mock(url="https://hcaptcha.com/widget")
    detached.is_detached.return_value = True
    active = Mock(url="https://challenges.cloudflare.com/widget")
    active.is_detached.return_value = False
    owner.child_frames = [detached, active]
    assert captcha._widgets(owner) == [{"kind": "turnstile", "ready": False}]


def test_checkbox_is_not_clicked_again_during_image_task(monkeypatch):
    owner = Mock()
    owner.evaluate.side_effect = lambda *a, **kw: [{"kind": "hcaptcha", "ready": False}]
    child = Mock(url="https://hcaptcha.com/checkbox")
    child.is_detached.return_value = False
    child.frame_element.return_value.bounding_box.return_value = {
        "x": 0,
        "y": 0,
        "width": 300,
        "height": 70,
    }
    owner.child_frames = [child]
    page = Mock(frames=[owner])
    solver = captcha._ChallengeSolver()
    assert not solver.ready_to_submit(page)
    monkeypatch.setattr(captcha.time, "monotonic", lambda: 1000000)
    assert not solver.ready_to_submit(page)
    page.mouse.click.assert_called_once()


@pytest.mark.parametrize(
    "host", ["www.s.to", "serienstream.to", "serienstream.cx", "186.2.175.5"]
)
def test_sto_redirect_between_its_own_hosts_is_not_a_provider(host):
    assert not captcha._is_provider_url(f"https://{host}/r?t=token", SOURCE)


def test_generic_solver_submits_completed_widgets_before_returning(
    browser, monkeypatch
):
    handle, page = browser
    monkeypatch.setattr(captcha, "_is_captcha_page_dom", lambda page: True)
    solver = Mock()
    solver.ready_to_submit.return_value = True
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)

    def submit(page):
        page.url = PLAYER
        return True

    monkeypatch.setattr(captcha, "_click_submit_button", submit)
    assert captcha.solve_captcha(SOURCE) == PLAYER
    solver.ready_to_submit.assert_called_once_with(page)
    handle.close.assert_called_once()
