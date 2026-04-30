# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Utility functions."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from ops import ActiveStatus, BlockedStatus, StatusBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import MigrationCheckError

if TYPE_CHECKING:
    from charm import TenantServiceOperatorCharm

logger = logging.getLogger(__name__)

CharmEventHandler = TypeVar("CharmEventHandler", bound=Callable[..., Any])
Condition = Callable[["TenantServiceOperatorCharm"], bool]


def leader_unit(func: CharmEventHandler) -> CharmEventHandler:
    """Decorator that ensures the handler only runs on the leader unit."""

    @wraps(func)
    def wrapper(charm: "TenantServiceOperatorCharm", *args: Any, **kwargs: Any) -> Any | None:
        if not charm.unit.is_leader():
            return None
        return func(charm, *args, **kwargs)

    return wrapper  # type: ignore[return-value]  # wrapper signature is compatible but mypy can't prove it for the generic TypeVar


def integration_existence(integration_name: str) -> Condition:
    """Create a condition that checks whether a relation exists."""

    def wrapped(charm: "TenantServiceOperatorCharm") -> bool:
        return bool(charm.model.relations[integration_name])

    return wrapped


database_integration_exists = integration_existence(DATABASE_INTEGRATION_NAME)
peer_integration_exists = integration_existence(PEER_INTEGRATION_NAME)
openfga_integration_exists = integration_existence(OPENFGA_INTEGRATION_NAME)
kratos_info_integration_exists = integration_existence(KRATOS_INFO_INTEGRATION_NAME)


def container_connectivity(charm: "TenantServiceOperatorCharm") -> bool:
    """Check if the workload container is reachable."""
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()


def database_resource_is_created(charm: "TenantServiceOperatorCharm") -> bool:
    """Check if the database resource has been created."""
    return charm.database_requirer.is_resource_created()


def migration_is_ready(charm: "TenantServiceOperatorCharm") -> bool:
    """Check if database migrations are up to date."""
    try:
        return not charm.migration_needed
    except MigrationCheckError:
        return False


def openfga_store_readiness(charm: "TenantServiceOperatorCharm") -> bool:
    """Check if the OpenFGA store is ready."""
    return charm.openfga_integration.is_store_ready()


def authentication_config_status(charm: "TenantServiceOperatorCharm") -> StatusBase:
    """Evaluate the authentication configuration and return the appropriate status."""
    oauth_config = charm._config.get_oauth_config()
    oauth_relation_ready = charm.oauth_integration.is_ready()

    if oauth_relation_ready and (
        oauth_config.get("authn_issuer") or oauth_config.get("authn_jwks_url")
    ):
        logger.error(
            "OAuth integration cannot be used with authn_issuer and authn_jwks_url config keys."
        )
        return ActiveStatus("Ignoring authentication config due to OAuth integration")

    if not oauth_relation_ready and (
        any(oauth_config.values()) and not oauth_config.get("authn_issuer")
    ):
        logger.error("authn_issuer config key must be set when using authentication config.")
        return BlockedStatus("Invalid authentication configuration")

    return ActiveStatus()


def authentication_config_is_valid(charm: "TenantServiceOperatorCharm") -> bool:
    """Check if the authentication configuration is valid."""
    status = authentication_config_status(charm)
    return isinstance(status, ActiveStatus)


NOOP_CONDITIONS: tuple[Condition, ...] = (
    container_connectivity,
    database_integration_exists,
    database_resource_is_created,
    authentication_config_is_valid,
)
