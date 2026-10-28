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
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
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
@pytest.mark.parametrize("path_type", ["absolute", "tilde", "relative"])
def test_single_ca_setting_is_used_by_http_clients(load_config, key, source, path_type):
    path = {
        "absolute": "/test/custom-ca.pem",
        "tilde": "~/Certificates with spaces/custom-ca.pem",
        "relative": "./Certificates with spaces/custom-ca.pem",
    }[path_type]
    expected = (
        Path.home() / "Certificates with spaces/custom-ca.pem"
        if path_type == "tilde"
        else Path(path)
    )
    values = {key: path}
    config, stored = load_config(
        file_values=values if source == "file" else None,
        process_values=values if source == "process" else None,
    )

    assert Path(config.CA_CERT_BUNDLE) == expected
    assert config.GLOBAL_SESSION.verify == config.CA_CERT_BUNDLE
    assert all(Path(os.environ[name]) == expected for name in CA_BUNDLE_ENV_VARS)
    if path_type != "tilde":
        assert config.CA_CERT_BUNDLE == path
    with curl_requests.Session() as session:
        assert session.verify == config.CA_CERT_BUNDLE
    if source == "file":
        assert stored[key] == path


def test_explicit_ca_paths_expand_independently(load_config):
    values = {
        "REQUESTS_CA_BUNDLE": "~/Certificates/requests.pem",
        "CURL_CA_BUNDLE": "relative/curl.pem",
        "SSL_CERT_FILE": "~/Certificates/ssl.pem",
    }

    config, stored = load_config(file_values=values)

    assert Path(config.CA_CERT_BUNDLE) == Path.home() / "Certificates/requests.pem"
    assert os.environ["CURL_CA_BUNDLE"] == "relative/curl.pem"
    assert Path(os.environ["SSL_CERT_FILE"]) == Path.home() / "Certificates/ssl.pem"
    assert {key: stored[key] for key in values} == values


@pytest.mark.parametrize("key", CA_BUNDLE_ENV_VARS)
def test_process_tilde_ca_path_overrides_file(load_config, key):
    config, stored = load_config(
        file_values={key: "~/Certificates/file.pem"},
        process_values={key: "~/Certificates/process.pem"},
    )

    assert Path(config.CA_CERT_BUNDLE) == Path.home() / "Certificates/process.pem"
    assert stored[key] == "~/Certificates/file.pem"


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
