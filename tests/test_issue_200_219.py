import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import niquests

from aniworld.extractors.provider import hanime_tv
from aniworld.models.common import common
from aniworld.models.common.common import (
    _build_blocking_player_command,
    _build_mpv_network_args,
)
from aniworld.playwright import captcha
from aniworld.playwright.captcha import _is_hanime_manifest_response


_HANIME_HTML = """
<meta property="og:title" content="Watch Example Episode Hentai Video">
<meta property="og:description" content="Example description">
<meta property="og:image" content="https://cdn.example.test/cover.webp">
<a href="/videos/hentai/example-episode">Example episode</a>
"""


class HanimeFallbackTests(unittest.TestCase):
    def test_fetch_uses_direct_html_when_available(self):
        response = Mock()
        response.text = _HANIME_HTML

        with (
            patch.object(hanime_tv.niquests, "get", return_value=response),
            patch.object(hanime_tv, "playwright_get_hanime_page_html") as browser_fetch,
        ):
            payload = hanime_tv.fetch_hanime_api_data("example-episode")

        self.assertEqual(payload["hentai_video"]["name"], "Example Episode")
        browser_fetch.assert_not_called()

    def test_fetch_uses_patchright_html_after_http_block(self):
        response = Mock()
        response.raise_for_status.side_effect = niquests.exceptions.HTTPError("403 Forbidden")

        with (
            patch.object(hanime_tv.niquests, "get", return_value=response),
            patch.object(
                hanime_tv,
                "playwright_get_hanime_page_html",
                return_value=_HANIME_HTML,
            ) as browser_fetch,
        ):
            payload = hanime_tv.fetch_hanime_api_data("example-episode")

        self.assertEqual(payload["hentai_video"]["slug"], "example-episode")
        browser_fetch.assert_called_once_with(
            "https://hanime.tv/videos/hentai/example-episode"
        )

    def test_fetch_reports_both_paths_when_patchright_cannot_load_the_page(self):
        response = Mock()
        response.raise_for_status.side_effect = niquests.exceptions.HTTPError("403 Forbidden")

        with (
            patch.object(hanime_tv.niquests, "get", return_value=response),
            patch.object(hanime_tv, "playwright_get_hanime_page_html", return_value=None),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "HTTP or Patchright"
            ) as error:
                hanime_tv.fetch_hanime_api_data("example-episode")

        self.assertIsInstance(error.exception.__cause__, niquests.exceptions.HTTPError)

    def test_hls_response_detection_accepts_extension_or_manifest_mime_type(self):
        self.assertTrue(
            _is_hanime_manifest_response(
                "https://cdn.example.test/master.m3u8?token=abc",
                200,
                "application/octet-stream",
            )
        )
        self.assertTrue(
            _is_hanime_manifest_response(
                "https://cdn.example.test/stream?token=abc",
                206,
                "application/vnd.apple.mpegurl; charset=utf-8",
            )
        )
        self.assertFalse(
            _is_hanime_manifest_response(
                "https://cdn.example.test/master.m3u8", 403, "application/vnd.apple.mpegurl"
            )
        )
        self.assertFalse(
            _is_hanime_manifest_response(
                "https://cdn.example.test/ad.js", 200, "application/javascript"
            )
        )

    def test_patchright_page_fallback_closes_the_browser_before_stopping_playwright(self):
        lifecycle = SimpleNamespace(stopped=False)

        class FakePage:
            def goto(self, *args, **kwargs):
                return None

            def content(self):
                return "<html><body>ok</body></html>"

        class FakeContext:
            def new_page(self):
                return FakePage()

        class FakeBrowser:
            closed_while_running = False

            def new_context(self, **kwargs):
                return FakeContext()

            def close(self):
                self.closed_while_running = not lifecycle.stopped

        browser = FakeBrowser()

        class FakePlaywright:
            chromium = SimpleNamespace(launch=lambda **kwargs: browser)

        class FakeSyncPlaywright:
            def __enter__(self):
                return FakePlaywright()

            def __exit__(self, *args):
                lifecycle.stopped = True

        with patch(
            "patchright.sync_api.sync_playwright", return_value=FakeSyncPlaywright()
        ):
            html = captcha.playwright_get_hanime_page_html(
                "https://hanime.tv/videos/hentai/example-episode"
            )

        self.assertEqual(html, "<html><body>ok</body></html>")
        self.assertTrue(browser.closed_while_running)


class PlayerHeaderTests(unittest.TestCase):
    def setUp(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Example)",
            "Referer": "https://voe.sx/",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Origin": "https://voe.sx",
        }

    def test_comma_containing_header_values_are_appended_individually(self):
        args = _build_mpv_network_args(self.headers)

        self.assertIn("--user-agent=Mozilla/5.0 (Example)", args)
        self.assertIn("--referrer=https://voe.sx/", args)
        self.assertIn(
            "--http-header-fields-append=Accept-Language: en-US,en;q=0.5", args
        )
        self.assertIn(
            "--http-header-fields-append=Accept-Encoding: gzip, deflate", args
        )
        self.assertNotIn("--http-header-fields=" + ",".join(self.headers.values()), args)
        self.assertFalse(any(arg.startswith("--http-header-fields=") for arg in args))

    def test_iina_keeps_raw_mpv_options_after_its_delimiter(self):
        options = ["--no-ytdl", "--http-header-fields-append=Accept: */*"]

        command = _build_blocking_player_command(
            "/Applications/IINA.app/Contents/MacOS/IINA",
            "https://cdn.example.test/master.m3u8",
            options,
        )

        self.assertEqual(
            command,
            [
                "/Applications/IINA.app/Contents/MacOS/IINA",
                "--keep-running",
                "https://cdn.example.test/master.m3u8",
                "--",
                *options,
            ],
        )

    def test_mpv_receives_the_same_options_without_an_iina_delimiter(self):
        options = _build_mpv_network_args(self.headers)

        command = _build_blocking_player_command(
            "/opt/local/bin/mpv",
            "https://cdn.example.test/master.m3u8",
            options,
        )

        self.assertEqual(command[:2], ["/opt/local/bin/mpv", "https://cdn.example.test/master.m3u8"])
        self.assertNotIn("--", command)
        self.assertEqual(command[2:], options)


class _WatchEpisode:
    _file_name = "Example S01E01"
    selected_provider = "VOE"
    stream_url = "https://cdn.example.test/master.m3u8"

    def provider_attempt_order(self):
        return ("VOE",)


class PlayerCommandIntegrationTests(unittest.TestCase):
    def _run_watch(self, player_path):
        process = Mock(returncode=0)
        with (
            patch.object(common, "get_player_path", return_value=player_path),
            patch.object(common.subprocess, "run", return_value=process) as run,
            patch.dict("os.environ", {"ANIWORLD_ANISKIP": "0"}, clear=False),
        ):
            common.watch(_WatchEpisode())
        return run.call_args.args[0]

    def test_watch_builds_a_valid_mpv_command_with_provider_headers(self):
        command = self._run_watch("/opt/local/bin/mpv")

        self.assertEqual(command[:2], ["/opt/local/bin/mpv", _WatchEpisode.stream_url])
        self.assertIn("--user-agent=" + common.PROVIDER_HEADERS_W["VOE"]["User-Agent"], command)
        self.assertIn("--referrer=https://voe.sx/", command)
        self.assertIn(
            "--http-header-fields-append=Accept-Language: en-US,en;q=0.5", command
        )
        self.assertFalse(any(arg.startswith("--http-header-fields=") for arg in command))

    def test_watch_places_iina_mpv_options_after_the_delimiter(self):
        command = self._run_watch("/Applications/IINA.app/Contents/MacOS/IINA")

        self.assertEqual(command[:4], [
            "/Applications/IINA.app/Contents/MacOS/IINA",
            "--keep-running",
            _WatchEpisode.stream_url,
            "--",
        ])
        self.assertIn("--user-agent=" + common.PROVIDER_HEADERS_W["VOE"]["User-Agent"], command[4:])

    def test_syncplay_forwards_the_same_safe_header_arguments_to_mpv(self):
        process = Mock(returncode=0)
        with (
            patch.object(common, "get_syncplay_path", return_value="syncplay"),
            patch.object(common, "get_player_path", return_value="mpv"),
            patch.object(
                common,
                "_resolve_stream_url_with_fallback",
                return_value=(_WatchEpisode.stream_url, "VOE"),
            ),
            patch.object(common.subprocess, "run", return_value=process) as run,
            patch.dict(
                "os.environ",
                {
                    "ANIWORLD_ANISKIP": "0",
                    "ANIWORLD_SYNCPLAY_USERNAME": "test-user",
                },
                clear=False,
            ),
        ):
            common.syncplay(_WatchEpisode())

        command = run.call_args.args[0]
        mpv_options = command[command.index("--") + 1 :]
        self.assertIn("--user-agent=" + common.PROVIDER_HEADERS_W["VOE"]["User-Agent"], mpv_options)
        self.assertIn(
            "--http-header-fields-append=Accept-Encoding: gzip, deflate", mpv_options
        )
        self.assertFalse(
            any(arg.startswith("--http-header-fields=") for arg in mpv_options)
        )


if __name__ == "__main__":
    unittest.main()
