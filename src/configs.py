# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's config."""

from typing import Any, Mapping, TypeAlias, cast

from ops import ConfigData

from env_vars import EnvVars

ServiceConfigs: TypeAlias = Mapping[str, Any]


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def get_oauth_config(self) -> dict[str, str | None]:
        """Get OAuth config."""
        return {
            k: cast(str, v)
            for k in [
                "authn_allowed_subjects",
                "authn_allowed_scope",
                "authn_issuer",
                "authn_jwks_url",
            ]
            if (v := self._config.get(k))
        }

    def get_missing_config_keys(self) -> list:
        """Get missing config keys."""
        return []

    def to_env_vars(self) -> EnvVars:
        """Get config env vars."""
        return {
            "LOG_LEVEL": self._config["log_level"].upper(),
            "HTTP_PROXY": self._config.get("http_proxy"),
            "HTTPS_PROXY": self._config.get("https_proxy"),
            "NO_PROXY": self._config.get("no_proxy"),
            "INVITATION_LIFETIME": self._config.get("invitation_lifetime", "24h"),
        }
