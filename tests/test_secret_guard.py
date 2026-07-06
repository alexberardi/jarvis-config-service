"""Boot-time + request-time guards on placeholder/weak admin tokens.

Policy (same as jarvis-auth's enforce_secret_security): warn everywhere, but
only ABORT startup when JARVIS_ENV=production — a dev/self-host box still boots
on a not-yet-hardened default, while prod refuses to run with a publicly-known
admin token on the service that bootstraps the whole cluster.

Request-time: a shipped template placeholder must never authenticate as the
admin token, even outside production and even if the server itself was left
configured with one.
"""
import logging

import pytest

from app.config import (
    Settings,
    enforce_secret_security,
    get_settings,
    is_placeholder_token,
)

STRONG = "x" * 40


def _settings(token: str = STRONG, env: str = "") -> Settings:
    s = Settings()
    s.ADMIN_TOKEN = token
    s.JARVIS_ENV = env
    return s


class TestIsPlaceholderToken:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "change-me",
            "CHANGE-ME",
            "changeme",
            "change_me",
            "__set_me__",
            "__SET_ME__",
            "change-me-to-something-secure",
            "CHANGE_ME_config_admin_token",
            None,
        ],
    )
    def test_placeholders_detected(self, value):
        assert is_placeholder_token(value) is True

    def test_strong_token_not_flagged(self):
        assert is_placeholder_token(STRONG) is False


class TestInsecureSecrets:
    def test_strong_token_has_no_problems(self):
        assert _settings().insecure_secrets() == []

    def test_placeholder_token_flagged(self):
        problems = _settings(token="change-me-to-something-secure").insecure_secrets()
        assert "JARVIS_CONFIG_ADMIN_TOKEN" in problems

    def test_short_token_flagged(self):
        assert "JARVIS_CONFIG_ADMIN_TOKEN" in _settings(token="short").insecure_secrets()

    def test_empty_token_flagged(self):
        assert "JARVIS_CONFIG_ADMIN_TOKEN" in _settings(token="").insecure_secrets()


class TestIsProduction:
    @pytest.mark.parametrize("value", ["production", "PROD", " Prod "])
    def test_production_values(self, value):
        assert _settings(env=value).is_production is True

    @pytest.mark.parametrize("value", ["development", "dev", "staging", ""])
    def test_non_production_values(self, value):
        assert _settings(env=value).is_production is False


class TestEnforce:
    def test_prod_with_placeholder_token_raises(self):
        cfg = _settings(token="change-me-to-something-secure", env="production")
        with pytest.raises(RuntimeError, match="Refusing to start in production"):
            enforce_secret_security(cfg, logging.getLogger("test"))

    def test_dev_with_placeholder_token_warns_not_raises(self, caplog):
        cfg = _settings(token="change-me-to-something-secure", env="development")
        with caplog.at_level(logging.WARNING):
            enforce_secret_security(cfg, logging.getLogger("test"))  # must not raise
        assert any("Insecure admin config" in r.message for r in caplog.records)

    def test_prod_with_strong_token_is_silent(self):
        cfg = _settings(env="production")
        enforce_secret_security(cfg, logging.getLogger("test"))  # no raise


class TestRequestTimePlaceholderRejection:
    def test_placeholder_token_rejected_even_when_server_configured_with_it(
        self, client, sample_service_data, monkeypatch
    ):
        monkeypatch.setattr(
            get_settings(), "ADMIN_TOKEN", "change-me-to-something-secure"
        )
        response = client.post(
            "/services",
            json=sample_service_data,
            headers={"X-Admin-Token": "change-me-to-something-secure"},
        )
        assert response.status_code == 401

    def test_placeholder_token_rejected_against_strong_server_token(
        self, client, sample_service_data
    ):
        response = client.post(
            "/services",
            json=sample_service_data,
            headers={"X-Admin-Token": "__SET_ME__"},
        )
        assert response.status_code == 401

    def test_real_token_still_works(self, client, admin_headers, sample_service_data):
        response = client.post(
            "/services", json=sample_service_data, headers=admin_headers
        )
        assert response.status_code == 201
