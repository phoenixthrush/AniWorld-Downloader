from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

from aniworld.config import GLOBAL_SESSION, STO_DOMAINS, STO_IP
from aniworld.models.s_to import http


class FakeSession:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        text, status = reply

        def raise_for_status():
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")

        return SimpleNamespace(
            text=text,
            status_code=status,
            url=url,
            raise_for_status=raise_for_status,
        )


@pytest.fixture(autouse=True)
def reset_active_host():
    previous = http._active_idx
    http._active_idx = 0
    yield
    http._active_idx = previous


def test_empty_response_falls_back_to_next_domain():
    session = FakeSession([(None, 200), ("<html>working</html>", 200)])

    response = http.sto_get(
        "https://serienstream.to/suche?term=haunted+hotel", session=session
    )

    assert response.text == "<html>working</html>"
    assert [call[0] for call in session.calls] == [
        f"https://{STO_DOMAINS[0]}/suche?term=haunted+hotel",
        f"https://{STO_DOMAINS[1]}/suche?term=haunted+hotel",
    ]
    assert http.sto_host() == STO_DOMAINS[1]


def test_invalid_body_rebuilds_the_calling_threads_session(monkeypatch):
    sessions = iter(
        [
            FakeSession([(None, 200)]),
            FakeSession([("<html>working</html>", 200)]),
        ]
    )
    http.reset_sto_session()
    monkeypatch.setattr(http, "_new_session", lambda: next(sessions))

    response = http.sto_get("https://serienstream.to/suche", params={"term": "from"})

    assert response.text == "<html>working</html>"
    assert http.sto_host() == STO_DOMAINS[0]
    http.reset_sto_session()


def test_worker_threads_do_not_share_sessions(monkeypatch):
    created = []
    barrier = Barrier(4)

    def new_session():
        session = object()
        created.append(session)
        return session

    monkeypatch.setattr(http, "_new_session", new_session)

    def get_session(_):
        barrier.wait()
        first = http._session()
        assert http._session() is first
        return first

    with ThreadPoolExecutor(max_workers=4) as pool:
        sessions = list(pool.map(get_session, range(4)))

    assert len(created) == 4
    assert len({id(session) for session in sessions}) == 4


def test_existing_thread_session_receives_updated_captcha_headers(monkeypatch):
    fake = SimpleNamespace(headers={}, cookies={}, close=lambda: None)
    http.reset_sto_session()
    monkeypatch.setattr(http, "_new_session", lambda: fake)

    assert http._session() is fake
    monkeypatch.setitem(GLOBAL_SESSION.headers, "User-Agent", "captcha-browser-agent")
    assert http._session() is fake

    assert fake.headers["User-Agent"] == "captcha-browser-agent"
    assert fake.headers["Accept-Encoding"] == "gzip, deflate"
    http.reset_sto_session()


def test_challenge_and_http_error_fall_back_to_raw_ip():
    session = FakeSession(
        [
            ("<title>Just a moment...</title>", 200),
            ("service unavailable", 503),
            ("<html>working</html>", 200),
        ]
    )

    response = http.sto_get("https://serienstream.to/serie/from", session=session)

    assert response.text == "<html>working</html>"
    ip_url, ip_options = session.calls[-1]
    assert ip_url == f"https://{STO_IP}/serie/from"
    assert ip_options["verify"] is False
    assert ip_options["headers"]["Host"] == STO_DOMAINS[0]


def test_all_invalid_responses_raise_descriptive_error():
    session = FakeSession([(None, 200), (None, 200), (None, 200)])

    with pytest.raises(http.SerienstreamResponseError, match="invalid response body"):
        http.sto_get("https://serienstream.to/serie/from", session=session)


def test_response_text_does_not_include_query_in_error():
    response = SimpleNamespace(text=None)

    with pytest.raises(http.SerienstreamResponseError) as error:
        http.response_text(response, "https://serienstream.to/r?signed=secret")

    assert "signed" not in str(error.value)
    assert "secret" not in str(error.value)
