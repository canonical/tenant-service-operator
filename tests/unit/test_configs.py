# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest

from configs import CharmConfig


class TestCharmConfig:
    @pytest.fixture
    def full_config(self) -> dict:
        return {
            "log_level": "debug",
            "http_proxy": "http://proxy:6666",
            "https_proxy": "http://proxy:6666",
            "no_proxy": "localhost",
            "invitation_lifetime": "48h",
            "authorization_enabled": False,
            "authn_allowed_subjects": "user1",
            "authn_allowed_scope": "email",
            "authn_issuer": "https://issuer.example.com",
            "authn_jwks_url": "https://jwks.example.com",
        }

    @pytest.fixture
    def minimal_config(self) -> dict:
        return {
            "log_level": "info",
        }

    def test_to_env_vars(self, full_config: dict) -> None:
        config = CharmConfig(full_config)
        env = config.to_env_vars()

        assert env["LOG_LEVEL"] == "DEBUG"
        assert env["HTTP_PROXY"] == "http://proxy:6666"
        assert env["HTTPS_PROXY"] == "http://proxy:6666"
        assert env["NO_PROXY"] == "localhost"
        assert env["INVITATION_LIFETIME"] == "48h"
        assert "AUTHORIZATION_ENABLED" not in env
        assert "authn_allowed_subjects" not in env
        assert "authn_allowed_scope" not in env
        assert "authn_issuer" not in env
        assert "authn_jwks_url" not in env

    def test_to_env_vars_defaults(self, minimal_config: dict) -> None:
        config = CharmConfig(minimal_config)
        env = config.to_env_vars()

        assert env["LOG_LEVEL"] == "INFO"
        assert env["HTTP_PROXY"] is None
        assert env["HTTPS_PROXY"] is None
        assert env["NO_PROXY"] is None
        assert env["INVITATION_LIFETIME"] == "24h"
        assert "AUTHORIZATION_ENABLED" not in env

    def test_get_oauth_config(self, full_config: dict) -> None:
        config = CharmConfig(full_config)
        oauth = config.get_oauth_config()

        assert oauth["authn_allowed_subjects"] == "user1"
        assert oauth["authn_allowed_scope"] == "email"
        assert oauth["authn_issuer"] == "https://issuer.example.com"
        assert oauth["authn_jwks_url"] == "https://jwks.example.com"

    def test_get_oauth_config_empty(self, minimal_config: dict) -> None:
        config = CharmConfig(minimal_config)
        oauth = config.get_oauth_config()

        assert oauth == {}

    def test_get_missing_config_keys(self, minimal_config: dict) -> None:
        config = CharmConfig(minimal_config)
        missing = config.get_missing_config_keys()

        assert missing == []
