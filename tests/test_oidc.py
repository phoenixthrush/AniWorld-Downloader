"""SSO dependency failures should explain what actually failed to import."""

import builtins
import importlib.util
import logging

import pytest
from flask import Flask

from aniworld.web import auth


@pytest.fixture(params=["authlib", "requests"])
def auth_without_sso(request, monkeypatch):
    original_import = builtins.__import__

    def missing_dependency(name, *args, **kwargs):
        if name == "authlib.integrations.flask_client":
            raise ModuleNotFoundError(
                f"No module named '{request.param}'", name=request.param
            )
        return original_import(name, *args, **kwargs)

    # Load a separate instance so the simulated import cannot affect other tests.
    spec = importlib.util.spec_from_file_location(auth.__name__, auth.__file__)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", missing_dependency)
        spec.loader.exec_module(module)

    monkeypatch.setattr(module, "logger", logging.getLogger(__name__))
    monkeypatch.setenv("ANIWORLD_OIDC_ISSUER_URL", "https://sso.example.com")
    monkeypatch.setenv("ANIWORLD_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("ANIWORLD_OIDC_CLIENT_SECRET", "test-secret")
    return module, request.param


def test_missing_sso_dependency_logs_the_import_error(auth_without_sso, caplog):
    module, missing_module = auth_without_sso
    app = Flask(__name__)

    module.init_oidc(app)

    assert app.config["OIDC_ENABLED"] is False
    assert app.config["FORCE_SSO"] is False
    assert f"No module named '{missing_module}'" in caplog.text
    assert "aniworld[sso]" in caplog.text
    assert "authlib is not installed" not in caplog.text


def test_forced_sso_reports_the_missing_dependency(auth_without_sso):
    module, missing_module = auth_without_sso

    with pytest.raises(RuntimeError, match="SSO login is forced") as caught:
        module.init_oidc(Flask(__name__), force_sso=True)

    assert f"No module named '{missing_module}'" in str(caught.value)
    assert "aniworld[sso]" in str(caught.value)
    assert isinstance(caught.value.__cause__, ModuleNotFoundError)
    assert caught.value.__cause__.name == missing_module
