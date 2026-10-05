"""Certificate configuration is loaded before HTTP sessions are created."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import Mock

import certifi
import niquests
import pytest
from curl_cffi import requests as curl_requests
from dotenv import dotenv_values

from aniworld.env import CA_BUNDLE_ENV_VARS

SOURCE = Path(__file__).resolve().parents[1] / "src" / "aniworld" / "config.py"


@pytest.fixture
def load_config(monkeypatch, tmp_path):
    for key in CA_BUNDLE_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    app_dir = tmp_path / "config"
    app_dir.mkdir()
    env_path = app_dir / ".env"
    monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", str(app_dir))
    monkeypatch.setattr(certifi, "where", lambda: "/test/default-ca.pem")

    def load(file_values=None, process_values=None):
        env_path.write_text(
            "".join(f"{key}={value}\n" for key, value in (file_values or {}).items())
        )
        for key, value in (process_values or {}).items():
            monkeypatch.setenv(key, value)

        def session(**kwargs):
            # Defaults must already be applied when the client is constructed.
            assert all(key in os.environ for key in CA_BUNDLE_ENV_VARS)
            return Mock()

        monkeypatch.setattr(niquests, "Session", session)
        spec = importlib.util.spec_from_file_location("aniworld._test_config", SOURCE)
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        return config, dotenv_values(env_path)

    return load


@pytest.mark.parametrize("key", CA_BUNDLE_ENV_VARS)
@pytest.mark.parametrize("source", ["file", "process"])
def test_single_ca_setting_is_used_by_http_clients(load_config, key, source):
    path = "/test/custom-ca.pem"
    values = {key: path}
    config, stored = load_config(
        file_values=values if source == "file" else None,
        process_values=values if source == "process" else None,
    )

    assert config.CA_CERT_BUNDLE == path
    assert config.GLOBAL_SESSION.verify == path
    assert all(os.environ[name] == path for name in CA_BUNDLE_ENV_VARS)
    with curl_requests.Session() as session:
        assert session.verify == path
    if source == "file":
        assert stored[key] == path


@pytest.mark.parametrize("key", CA_BUNDLE_ENV_VARS)
def test_process_ca_setting_overrides_same_key_in_file(load_config, key):
    config, stored = load_config(
        file_values={key: "/test/file-ca.pem"},
        process_values={key: "/test/process-ca.pem"},
    )

    assert config.CA_CERT_BUNDLE == "/test/process-ca.pem"
    assert config.GLOBAL_SESSION.verify == "/test/process-ca.pem"
    assert stored[key] == "/test/file-ca.pem"


@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, "/test/default-ca.pem"),
        (
            {"SSL_CERT_FILE": "/test/ssl.pem", "CURL_CA_BUNDLE": "/test/curl.pem"},
            "/test/curl.pem",
        ),
        (
            {
                "SSL_CERT_FILE": "/test/ssl.pem",
                "CURL_CA_BUNDLE": "/test/curl.pem",
                "REQUESTS_CA_BUNDLE": "/test/requests.pem",
            },
            "/test/requests.pem",
        ),
    ],
)
def test_ca_precedence_preserves_explicit_values(load_config, values, expected):
    config, stored = load_config(file_values=values)

    assert config.CA_CERT_BUNDLE == expected
    assert config.GLOBAL_SESSION.verify == expected
    for key in CA_BUNDLE_ENV_VARS:
        assert os.environ[key] == values.get(key, expected)
    assert {key: stored[key] for key in values} == values
