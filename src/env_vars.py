# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class with the application's default env vars."""

from typing import Mapping, Protocol, TypeAlias, Union

from constants import GRPC_PORT, PORT

EnvVars: TypeAlias = Mapping[str, Union[str, bool]]

DEFAULT_CONTAINER_ENV = {
    "OTEL_HTTP_ENDPOINT": "",
    "OTEL_GRPC_ENDPOINT": "",
    "TRACING_ENABLED": False,
    "LOG_LEVEL": "info",
    "PORT": str(PORT),
    "GRPC_PORT": str(GRPC_PORT),
    "WEBHOOKS_API_TOKEN": "",
    "KRATOS_ADMIN_URL": "",
    "INVITATION_LIFETIME": "24h",
    "AUTHORIZATION_ENABLED": False,
    "AUTHENTICATION_ENABLED": False,
}


class EnvVarConvertible(Protocol):
    """An interface enforcing the contribution to workload service environment variables."""

    def to_env_vars(self) -> EnvVars:
        """Get default env vars."""
        ...
