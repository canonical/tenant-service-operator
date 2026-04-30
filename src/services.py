# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the charm's services."""

import copy
import logging

from ops import Container, ModelError, Unit
from ops.pebble import CheckStatus, Layer, LayerDict, ServiceInfo

from cli import CommandLine
from constants import (
    CERTIFICATES_FILE,
    GRPC_PORT,
    LOCAL_CERTIFICATES_FILE,
    PEBBLE_READY_CHECK_NAME,
    PORT,
    SERVICE_COMMAND,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleError
from integrations import OpenFGAIntegrationData

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT: LayerDict = {
    "summary": "tenant-service-operator layer",
    "description": "pebble config layer for tenant-service-operator",
    "services": {
        WORKLOAD_CONTAINER: {
            "override": "replace",
            "summary": "entrypoint of the tenant-service-operator image",
            "command": f"{SERVICE_COMMAND}",
            "startup": "disabled",
        }
    },
    "checks": {
        PEBBLE_READY_CHECK_NAME: {
            "override": "replace",
            "http": {"url": f"http://localhost:{PORT}/api/v0/status"},
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""
        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        """Get the workload version."""
        if not self._version:
            self._version = self._cli.get_service_version() or ""
        return self._version

    def get_service(self) -> ServiceInfo | None:
        """Get the pebble service info."""
        try:
            return self._container.get_service(WORKLOAD_SERVICE)
        except (ModelError, ConnectionError) as e:
            logger.error("Failed to get pebble service: %s", e)

    def set_version(self) -> None:
        """Set the workload version on the Juju unit."""
        try:
            self._unit.set_workload_version(self.version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)

    def is_running(self) -> bool:
        """Check if the workload service is running and healthy."""
        if not (service := self.get_service()):
            return False
        if not service.is_running():
            return False
        c = self._container.get_checks().get(PEBBLE_READY_CHECK_NAME)
        if not c:
            return False
        return c.status == CheckStatus.UP

    def is_failing(self) -> bool:
        """Check if the workload service health check is failing."""
        if not (service := self.get_service()):
            return False
        if not service.is_running():
            return False
        if not (c := self._container.get_checks().get(PEBBLE_READY_CHECK_NAME)):
            return False
        return c.status == CheckStatus.DOWN

    def open_port(self) -> None:
        """Open the HTTP and gRPC ports on the Juju unit."""
        self._unit.open_port(protocol="tcp", port=PORT)
        self._unit.open_port(protocol="tcp", port=GRPC_PORT)

    def create_openfga_model(self, openfga_data: OpenFGAIntegrationData) -> str:
        """Create an OpenFGA authorization model.

        Args:
            openfga_data: The OpenFGA integration data.

        Returns:
            The model ID, or an empty string if creation failed.
        """
        model_id = self._cli.create_openfga_model(
            openfga_data.url,
            openfga_data.api_token,
            openfga_data.store_id,
        )
        return model_id or ""

    def update_ca_certs(self) -> bool:
        """Update the CA certificates in the workload container.

        Returns:
            True if the certificate bundle was updated, False if it was already current.
        """
        ca_certs = LOCAL_CERTIFICATES_FILE.read_text() if LOCAL_CERTIFICATES_FILE.exists() else ""
        current = (
            self._container.pull(CERTIFICATES_FILE).read()
            if self._container.exists(CERTIFICATES_FILE)
            else ""
        )
        if current == ca_certs:
            return False
        self._container.push(CERTIFICATES_FILE, ca_certs, make_dirs=True)
        return True


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_CONTAINER)
        self._layer_dict: LayerDict = copy.deepcopy(PEBBLE_LAYER_DICT)

    def _restart_service(self, restart: bool = False) -> None:
        """Restart or start the pebble service.

        Args:
            restart: If True, force a restart. Otherwise, start or replan.
        """
        if restart:
            self._container.restart(WORKLOAD_SERVICE)
        elif not self._container.get_service(WORKLOAD_SERVICE).is_running():
            self._container.start(WORKLOAD_SERVICE)
        else:
            self._container.replan()

    def plan(self, layer: Layer, force_restart: bool = False) -> None:
        """Apply a pebble layer and restart the workload service.

        Args:
            layer: The pebble layer to apply.
            force_restart: If True, restart the service even if the layer is unchanged.
                Use this when non-layer resources (e.g. CA certificates) have changed.

        Raises:
            PebbleError: If the service fails to restart.
        """
        self._container.add_layer(WORKLOAD_SERVICE, layer, combine=True)
        try:
            self._restart_service(restart=force_restart)
        except Exception as e:
            raise PebbleError(f"Pebble failed to restart the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        """Render a pebble layer with environment variables from the given sources.

        Precedence (highest wins): later sources override earlier ones.
        DEFAULT_CONTAINER_ENV is the base; each successive source's
        ``to_env_vars()`` output is merged on top.  The intended order
        (lowest → highest) should be: tracing, database, secrets, charm
        config, OpenFGA model, OpenFGA integration, OAuth, Kratos info.

        Args:
            *env_var_sources: Objects implementing EnvVarConvertible.

        Returns:
            The rendered pebble Layer.
        """
        env_vars: dict[str, str | bool] = dict(DEFAULT_CONTAINER_ENV)
        for source in env_var_sources:
            env_vars.update(source.to_env_vars())
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars
        return Layer(self._layer_dict)
