#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re
from pathlib import Path
from typing import Callable

import jubilant
import pytest
import requests
from integration.conftest import integrate_dependencies
from integration.constants import (
    APP_IMAGE,
    APP_NAME,
    DB_APP,
    INGRESS_DOMAIN,
    KRATOS_APP,
    KRATOS_CHARM,
    TRAEFIK_APP,
    TRAEFIK_CHARM,
)
from integration.utils import (
    StatusPredicate,
    all_active,
    and_,
    any_error,
    is_blocked,
    remove_integration,
    unit_number,
)

from src.constants import DATABASE_INTEGRATION_NAME, KRATOS_INFO_INTEGRATION_NAME

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy the charm-under-test together with related charms."""
    juju.deploy(
        DB_APP,
        channel="14/stable",
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_APP,
        channel="latest/stable",
        config={"external_hostname": INGRESS_DOMAIN},
        trust=True,
    )
    juju.deploy(
        KRATOS_CHARM,
        app=KRATOS_APP,
        channel="latest/edge",
        trust=True,
    )

    juju.deploy(
        str(local_charm),
        app=APP_NAME,
        resources={"oci-image": APP_IMAGE},
        config={"authorization_enabled": "false"},
        trust=True,
    )

    integrate_dependencies(juju)

    juju.wait(
        ready=all_active(APP_NAME, DB_APP, TRAEFIK_APP, KRATOS_APP),
        error=any_error(APP_NAME, DB_APP, TRAEFIK_APP, KRATOS_APP),
        timeout=15 * 60,
    )


def test_app_health(
    juju: jubilant.Juju,
    public_address: str,
    http_client: requests.Session,
) -> None:
    """Test workload health endpoint is accessible."""
    resp = http_client.get(f"http://{public_address}:8080/api/v0/status")
    resp.raise_for_status()


def test_create_tenant_action(juju: jubilant.Juju) -> None:
    """Test the create-tenant action."""
    result = juju.run(f"{APP_NAME}/leader", "create-tenant", params={"name": "test-tenant"})
    assert result.status == "completed"
    assert "output" in result.results


def test_list_tenants_action(juju: jubilant.Juju) -> None:
    """Test the list-tenants action."""
    result = juju.run(f"{APP_NAME}/leader", "list-tenants")
    assert result.status == "completed"
    assert "output" in result.results


def _extract_tenant_id(output: str) -> str | None:
    """Extract a tenant ID (ULID or UUID) from CLI output."""
    match = re.search(r"\b([0-9A-HJKMNP-TV-Z]{26})\b", output)
    if match:
        return match.group(1)
    match = re.search(
        r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
        output,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def test_tenant_lifecycle(juju: jubilant.Juju) -> None:
    """Test the full tenant lifecycle: create, update, deactivate, activate, delete."""
    result = juju.run(f"{APP_NAME}/leader", "create-tenant", params={"name": "lifecycle-tenant"})
    assert result.status == "completed"
    output = result.results.get("output", "")
    tenant_id = _extract_tenant_id(output)
    assert tenant_id, f"Could not extract tenant ID from create output: {output!r}"

    result = juju.run(
        f"{APP_NAME}/leader",
        "update-tenant",
        params={"tenant-id": tenant_id, "name": "lifecycle-tenant-updated"},
    )
    assert result.status == "completed"

    result = juju.run(f"{APP_NAME}/leader", "deactivate-tenant", params={"tenant-id": tenant_id})
    assert result.status == "completed"

    result = juju.run(f"{APP_NAME}/leader", "activate-tenant", params={"tenant-id": tenant_id})
    assert result.status == "completed"

    result = juju.run(f"{APP_NAME}/leader", "delete-tenant", params={"tenant-id": tenant_id})
    assert result.status == "completed"


def test_user_management(juju: jubilant.Juju) -> None:
    """Test user management actions for a tenant."""
    result = juju.run(f"{APP_NAME}/leader", "create-tenant", params={"name": "user-mgmt-tenant"})
    assert result.status == "completed"
    tenant_id = _extract_tenant_id(result.results.get("output", ""))
    assert tenant_id, "Could not extract tenant ID for user management tests"

    try:
        result = juju.run(
            f"{APP_NAME}/leader", "list-tenant-users", params={"tenant-id": tenant_id}
        )
        assert result.status == "completed"
        assert "output" in result.results
    finally:
        juju.run(f"{APP_NAME}/leader", "delete-tenant", params={"tenant-id": tenant_id})


def test_scale_up(juju: jubilant.Juju) -> None:
    """Test scaling up to verify HA and leader election."""
    target_unit_number = 2
    juju.cli("scale-application", APP_NAME, str(target_unit_number))

    juju.wait(
        ready=and_(
            all_active(APP_NAME),
            unit_number(APP_NAME, target_unit_number),
        ),
        error=any_error(APP_NAME),
        timeout=5 * 60,
    )


@pytest.mark.parametrize(
    "remote_app_name,integration_name,is_status",
    [
        (DB_APP, DATABASE_INTEGRATION_NAME, is_blocked),
        (KRATOS_APP, KRATOS_INFO_INTEGRATION_NAME, is_blocked),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    is_status: Callable[[str], StatusPredicate],
) -> None:
    """Test removing and re-adding integration."""
    with remove_integration(juju, remote_app_name, integration_name):
        juju.wait(
            ready=is_status(APP_NAME),
            error=any_error(APP_NAME),
            timeout=10 * 60,
        )
    juju.wait(
        ready=all_active(APP_NAME, remote_app_name),
        error=any_error(APP_NAME, remote_app_name),
        timeout=10 * 60,
    )


def test_scale_down(juju: jubilant.Juju) -> None:
    """Test scaling down to verify cluster stability."""
    target_unit_num = 1
    juju.cli("scale-application", APP_NAME, str(target_unit_num))

    juju.wait(
        ready=and_(
            all_active(APP_NAME),
            unit_number(APP_NAME, target_unit_num),
        ),
        error=any_error(APP_NAME),
        timeout=5 * 60,
    )


@pytest.mark.teardown
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(APP_NAME, destroy_storage=True)
    juju.wait(lambda s: APP_NAME not in s.apps, timeout=1000)
