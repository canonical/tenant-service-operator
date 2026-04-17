#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re
from pathlib import Path

import jubilant
import pytest
import requests
from integration.constants import (
    APP_NAME,
    DB_APP,
    DB_CHARM,
    INGRESS_DOMAIN,
    METADATA,
    OPENFGA_APP,
    OPENFGA_CHARM,
    TRAEFIK_APP,
    TRAEFIK_CHARM,
)
from integration.utils import (
    remove_integration,
    unit_address,
    wait_for_active_idle,
    wait_for_status,
)

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
def test_build_and_deploy(
    juju: jubilant.Juju,
    local_charm: Path | str,
    charm_config: dict,
) -> None:
    """Build the charm-under-test and deploy it together with related charms."""
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}

    juju.deploy(
        str(local_charm),
        resources=resources,
        app=APP_NAME,
        config=charm_config,
    )

    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_APP,
        channel="latest/stable",
        config={"external_hostname": INGRESS_DOMAIN},
        trust=True,
    )

    juju.deploy(
        DB_CHARM,
        app=DB_APP,
        channel="14/stable",
        trust=True,
    )

    juju.deploy(
        OPENFGA_CHARM,
        app=OPENFGA_APP,
        channel="latest/edge",
        trust=True,
    )

    juju.integrate(TRAEFIK_APP, f"{APP_NAME}:internal-route")
    juju.integrate(DB_APP, APP_NAME)
    juju.integrate(DB_APP, OPENFGA_APP)
    juju.integrate(OPENFGA_APP, f"{APP_NAME}:openfga")

    wait_for_active_idle(
        juju,
        apps=[TRAEFIK_APP, DB_APP, OPENFGA_APP, APP_NAME],
        timeout=1000,
    )


def test_app_health(
    juju: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    """Test workload health endpoint is accessible."""
    public_address = unit_address(juju, app_name=APP_NAME, unit_num=0)
    resp = http_client.get(f"http://{public_address}:8080/api/v0/status")
    resp.raise_for_status()


def test_ingress_route(
    juju: jubilant.Juju,
    http_client: requests.Session,
) -> None:
    """Test workload is accessible via Traefik ingress."""
    address = unit_address(juju, app_name=TRAEFIK_APP, unit_num=0)
    url = f"https://{address}/{juju.juju}-{APP_NAME}/api/v0/status"
    resp = http_client.get(url)
    resp.raise_for_status()


def test_scaling_up(juju: jubilant.Juju) -> None:
    """Test scaling up to verify HA and leader election."""
    juju.cli("scale-application", APP_NAME, "2")
    wait_for_active_idle(juju, apps=[APP_NAME], timeout=1000)


def test_create_tenant_action(juju: jubilant.Juju) -> None:
    """Test the create-tenant action."""
    result = juju.run_action(f"{APP_NAME}/leader", "create-tenant", name="test-tenant")
    assert result.status == "completed"
    assert "output" in result.results


def test_list_tenants_action(juju: jubilant.Juju) -> None:
    """Test the list-tenants action."""
    result = juju.run_action(f"{APP_NAME}/leader", "list-tenants")
    assert result.status == "completed"
    assert "output" in result.results


def _extract_tenant_id(output: str) -> str | None:
    """Extract a tenant ID (ULID or UUID) from CLI output."""
    # Try ULID first (26 Crockford Base32 chars)
    match = re.search(r"\b([0-9A-HJKMNP-TV-Z]{26})\b", output)
    if match:
        return match.group(1)
    # Fall back to UUID
    match = re.search(
        r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
        output,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def test_tenant_lifecycle(juju: jubilant.Juju) -> None:
    """Test the full tenant lifecycle: create, update, deactivate, activate, delete."""
    # Create
    result = juju.run_action(f"{APP_NAME}/leader", "create-tenant", name="lifecycle-tenant")
    assert result.status == "completed"
    output = result.results.get("output", "")
    tenant_id = _extract_tenant_id(output)
    assert tenant_id, f"Could not extract tenant ID from create output: {output!r}"

    # Update name
    result = juju.run_action(
        f"{APP_NAME}/leader",
        "update-tenant",
        **{"tenant-id": tenant_id, "name": "lifecycle-tenant-updated"},
    )
    assert result.status == "completed"

    # Deactivate
    result = juju.run_action(f"{APP_NAME}/leader", "deactivate-tenant", **{"tenant-id": tenant_id})
    assert result.status == "completed"

    # Activate
    result = juju.run_action(f"{APP_NAME}/leader", "activate-tenant", **{"tenant-id": tenant_id})
    assert result.status == "completed"

    # Delete
    result = juju.run_action(f"{APP_NAME}/leader", "delete-tenant", **{"tenant-id": tenant_id})
    assert result.status == "completed"


def test_list_tenants_with_pagination(juju: jubilant.Juju) -> None:
    """Test the list-tenants action with explicit page-size."""
    result = juju.run_action(f"{APP_NAME}/leader", "list-tenants", **{"page-size": 10})
    assert result.status == "completed"
    assert "output" in result.results


def test_user_management(juju: jubilant.Juju) -> None:
    """Test user management actions for a tenant."""
    # Create a tenant to operate on
    result = juju.run_action(f"{APP_NAME}/leader", "create-tenant", name="user-mgmt-tenant")
    assert result.status == "completed"
    tenant_id = _extract_tenant_id(result.results.get("output", ""))
    assert tenant_id, "Could not extract tenant ID for user management tests"

    try:
        # List users (should be empty initially)
        result = juju.run_action(
            f"{APP_NAME}/leader", "list-tenant-users", **{"tenant-id": tenant_id}
        )
        assert result.status == "completed"
        assert "output" in result.results

        # List users with pagination
        result = juju.run_action(
            f"{APP_NAME}/leader",
            "list-tenant-users",
            **{"tenant-id": tenant_id, "page-size": 5},
        )
        assert result.status == "completed"

        # Invite user
        result = juju.run_action(
            f"{APP_NAME}/leader",
            "invite-user",
            **{
                "tenant-id": tenant_id,
                "email": "invited@example.com",
                "role": "member",
            },
        )
        assert result.status == "completed"

        # Provision user
        result = juju.run_action(
            f"{APP_NAME}/leader",
            "provision-user",
            **{
                "tenant-id": tenant_id,
                "email": "provisioned@example.com",
                "role": "member",
            },
        )
        assert result.status == "completed"
    finally:
        # Clean up
        juju.run_action(f"{APP_NAME}/leader", "delete-tenant", **{"tenant-id": tenant_id})


@pytest.mark.parametrize(
    "remote_app_name,integration_name,expected_status",
    [
        (TRAEFIK_APP, "internal-route", "active"),
        (DB_APP, "pg-database", "blocked"),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    expected_status: str,
) -> None:
    """Test removing and re-adding integration."""
    with remove_integration(juju, remote_app_name, integration_name):
        wait_for_status(juju, apps=[APP_NAME], status=expected_status, timeout=1000)

    wait_for_active_idle(juju, apps=[APP_NAME, remote_app_name], timeout=1000)


def test_scaling_down(juju: jubilant.Juju) -> None:
    """Test scaling down to verify cluster stability."""
    juju.cli("scale-application", APP_NAME, "1")
    wait_for_active_idle(juju, apps=[APP_NAME], timeout=1000)


@pytest.mark.skip_if_keep_models
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(APP_NAME, force=True, destroy_storage=True)
    juju.wait(lambda s: APP_NAME not in s.apps, timeout=1000)
