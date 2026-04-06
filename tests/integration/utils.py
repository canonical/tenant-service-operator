# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from contextlib import contextmanager
from typing import Iterator, Optional

import jubilant
import pytest
import yaml
from integration.constants import APP_NAME


def create_temp_juju_model(
    request: pytest.FixtureRequest, *, model: str = ""
) -> Iterator[jubilant.Juju]:
    """Create a temporary Juju model."""
    keep_models = bool(request.config.getoption("--keep-models"))

    with jubilant.temp_model(keep=keep_models) as juju:
        if model:
            assert juju.model is not None
            juju.destroy_model(juju.model, destroy_storage=True, force=True)

            try:
                juju.add_model(model)
            except jubilant.CLIError:
                juju.model = model

        juju.wait_timeout = 10 * 60

        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end="")


def get_unit_data(model: jubilant.Juju, unit_name: str) -> dict:
    """Get the data for a given unit."""
    stdout = model.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    model: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    """Get the integration data for a given integration."""
    data = get_unit_data(model, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    model: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    """Get the application data for a given integration."""
    data = get_integration_data(model, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def unit_address(model: jubilant.Juju, *, app_name: str, unit_num: int = 0) -> str:
    """Get the address of a unit."""
    status_yaml = model.cli("status", "--format", "yaml")
    status = yaml.safe_load(status_yaml)
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


def wait_for_active_idle(model: jubilant.Juju, apps: list[str], timeout: float = 1000) -> None:
    """Wait for all applications and their units to be active and idle."""

    def condition(s: jubilant.Status) -> bool:
        return jubilant.all_active(s, *apps) and jubilant.all_agents_idle(s, *apps)

    model.wait(condition, error=jubilant.any_error, timeout=timeout)


def wait_for_status(
    model: jubilant.Juju, apps: list[str], status: str, timeout: float = 1000
) -> None:
    """Wait for all applications and their units to reach the given status."""

    def condition(s: jubilant.Status) -> bool:
        return all(s.apps[app_name].app_status.current == status for app_name in apps)

    model.wait(condition, timeout=timeout)


@contextmanager
def remove_integration(
    model: jubilant.Juju, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Context manager to remove and then re-add an integration."""
    model.cli("remove-relation", f"{APP_NAME}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        model.integrate(remote_app_name, f"{APP_NAME}:{integration_name}")
