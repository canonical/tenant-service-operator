# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import testing
from ops.model import Container, Unit
from pytest_mock import MockerFixture

from charm import TenantServiceOperatorCharm
from constants import OAUTH_INTEGRATION_NAME, OPENFGA_MODEL_ID, WORKLOAD_CONTAINER


# ---------------------------------------------------------------------------
# create_state() — module-level factory (NOT a fixture)
# ---------------------------------------------------------------------------
def create_state(
    leader: bool = True,
    secrets: list | None = None,
    relations: list | None = None,
    containers: list | None = None,
    config: dict | None = None,
    can_connect: bool = True,
    workload_version: str = "1.0.0",
) -> testing.State:
    """Build a complete State with sensible defaults for tenant-service tests."""
    if secrets is None:
        secrets = []
    if relations is None:
        relations = []
    if containers is None:
        containers = [
            testing.Container(
                WORKLOAD_CONTAINER,
                can_connect=can_connect,
                execs={
                    testing.Exec(
                        command_prefix=["tenant-service", "version"],
                        return_code=0,
                        stdout=f"App Version: {workload_version}",
                    ),
                    testing.Exec(
                        command_prefix=["tenant-service", "migrate", "check"],
                        return_code=0,
                        stdout='{"status": "ok"}',
                    ),
                    testing.Exec(
                        command_prefix=["tenant-service", "migrate", "up"],
                        return_code=0,
                        stdout="",
                    ),
                    testing.Exec(
                        command_prefix=["tenant-service", "create-fga-model"],
                        return_code=0,
                        stdout='{"model_id": "01HT27W9Y00000000000000000"}',
                    ),
                },
            )
        ]
    if config is None:
        config = {}

    return testing.State(
        leader=leader,
        secrets=secrets,
        containers=containers,
        relations=relations,
        config=config,
        model=testing.Model(name="test-model"),
    )


# ---------------------------------------------------------------------------
# Resource-patch mocks (autouse)
# ---------------------------------------------------------------------------
@pytest.fixture()
def mocked_resource_patch(mocker: MockerFixture) -> MagicMock:
    mocked = mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocked.return_value.is_failed.return_value = (False, "")
    mocked.return_value.is_in_progress.return_value = False
    return mocked


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture, mocked_resource_patch: MagicMock) -> None:
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


# ---------------------------------------------------------------------------
# OpenFGA autouse mock
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mocked_openfga_integration(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.OpenFGAIntegration.is_store_ready", return_value=True)


# ---------------------------------------------------------------------------
# Subprocess autouse mock
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mocked_subprocess_run(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("subprocess.run")


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
@pytest.fixture
def context() -> testing.Context:
    return testing.Context(TenantServiceOperatorCharm)


# ---------------------------------------------------------------------------
# Container fixture (for tests that need a direct reference)
# ---------------------------------------------------------------------------
@pytest.fixture
def container() -> testing.Container:
    return testing.Container(
        WORKLOAD_CONTAINER,
        can_connect=True,
        execs={
            testing.Exec(
                command_prefix=["tenant-service", "version"],
                return_code=0,
                stdout="App Version: 1.0.0",
            ),
            testing.Exec(
                command_prefix=["tenant-service", "migrate", "check"],
                return_code=0,
                stdout='{"status": "ok"}',
            ),
            testing.Exec(
                command_prefix=["tenant-service", "migrate", "up"],
                return_code=0,
                stdout="",
            ),
            testing.Exec(
                command_prefix=["tenant-service", "create-fga-model"],
                return_code=0,
                stdout='{"model_id": "01HT27W9Y00000000000000000"}',
            ),
        },
    )


# ---------------------------------------------------------------------------
# Charm service mocks
# ---------------------------------------------------------------------------
@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="1.10.0"
    )


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.TenantServiceOperatorCharm._holistic_handler")


@pytest.fixture
def mocked_is_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService.is_running", return_value=True)


@pytest.fixture
def mocked_open_port(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService.open_port")


# ---------------------------------------------------------------------------
# Component-test mocks (MagicMock-based)
# ---------------------------------------------------------------------------
@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


# ---------------------------------------------------------------------------
# Relation fixtures (standalone)
# ---------------------------------------------------------------------------
@pytest.fixture
def internal_route_integration_data() -> dict:
    return {
        "external_host": "some-host",
        "scheme": "http",
    }


@pytest.fixture
def internal_route_integration(internal_route_integration_data: dict) -> testing.Relation:
    return testing.Relation(
        endpoint="internal-route",
        interface="traefik_route",
        remote_app_name="traefik",
        remote_app_data=internal_route_integration_data,
    )


@pytest.fixture
def database_relation_data() -> dict:
    return {
        "endpoints": "postgres-k8s-primary.namespace.svc.cluster.local:5432",
        "username": "username",
        "password": "password",
    }


@pytest.fixture
def database_relation(database_relation_data: dict) -> testing.Relation:
    return testing.Relation(
        endpoint="pg-database",
        interface="postgresql_client",
        remote_app_name="postgres-k8s",
        remote_app_data=database_relation_data,
    )


@pytest.fixture
def openfga_secret() -> testing.Secret:
    return testing.Secret(
        tracked_content={"token": "token"},
        owner=None,
    )


@pytest.fixture
def openfga_relation_data(openfga_secret: testing.Secret) -> dict:
    return {
        "token_secret_id": openfga_secret.id,
        "store_id": "some-store-id",
        "grpc_api_url": "http://openfga:8081",
        "http_api_url": "http://openfga:8080",
    }


@pytest.fixture
def openfga_relation(openfga_relation_data: dict) -> testing.Relation:
    return testing.Relation(
        endpoint="openfga",
        interface="openfga",
        remote_app_name="openfga",
        remote_app_data=openfga_relation_data,
    )


@pytest.fixture
def peer_relation(
    mocked_workload_service_version: MagicMock, openfga_model_id: str
) -> testing.PeerRelation:
    return testing.PeerRelation(
        endpoint="tenant-service",
        interface="tenant_service_peers",
        local_app_data={
            mocked_workload_service_version.return_value: json.dumps(
                {OPENFGA_MODEL_ID: openfga_model_id}
            )
        },
    )


@pytest.fixture
def kratos_info_relation() -> testing.Relation:
    return testing.Relation(
        endpoint="kratos-info",
        interface="kratos_info",
        remote_app_name="kratos",
        remote_app_data={"admin_url": "http://kratos-admin:4434"},
    )


@pytest.fixture
def oauth_relation() -> testing.Relation:
    return testing.Relation(
        endpoint=OAUTH_INTEGRATION_NAME,
        interface="oauth",
        remote_app_name="hydra",
        remote_app_data={
            "issuer_url": "https://hydra.example.com",
            "authorization_endpoint": "https://hydra.example.com/oauth2/auth",
            "token_endpoint": "https://hydra.example.com/oauth2/token",
            "introspection_endpoint": "https://hydra.example.com/admin/oauth2/introspect",
            "userinfo_endpoint": "https://hydra.example.com/userinfo",
            "jwks_endpoint": "https://hydra.example.com/.well-known/jwks.json",
            "scope": "openid",
            "client_id": "tenant-service-client-id",
            "client_secret_id": "tenant-service-client-secret",
        },
    )


@pytest.fixture
def certificate_transfer_relation() -> testing.Relation:
    return testing.Relation(
        endpoint="receive-ca-cert",
        interface="certificate_transfer",
        remote_app_name="cert-authority",
        remote_units_data={
            0: {
                "ca": "some-ca-cert",
                "certificate": "some-cert",
                "chain": "some-chain",
            }
        },
    )


# ---------------------------------------------------------------------------
# Secrets & tokens
# ---------------------------------------------------------------------------
@pytest.fixture()
def api_token() -> str:
    return "secret"


@pytest.fixture()
def api_token_secret(api_token: str) -> testing.Secret:
    return testing.Secret(
        tracked_content={"api-token": api_token},
        label="apitokensecret",
    )


@pytest.fixture
def openfga_model_id() -> str:
    return "01HT27W9Y00000000000000000"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@pytest.fixture
def charm_config() -> dict:
    return {}


# ---------------------------------------------------------------------------
# Condition mock fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mocked_container_connectivity(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.container_connectivity", return_value=True)


@pytest.fixture
def mocked_secrets_is_ready(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.Secrets.is_ready", return_value=True)


@pytest.fixture
def mocked_get_missing_config_keys(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.CharmConfig.get_missing_config_keys", return_value=[])


@pytest.fixture
def mocked_database_integration_exists(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.database_integration_exists", return_value=True)


@pytest.fixture
def mocked_database_resource_is_created(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.database_resource_is_created", return_value=True)


@pytest.fixture
def mocked_migration_is_ready(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.migration_is_ready", return_value=True)


@pytest.fixture
def mocked_openfga_integration_exists(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.openfga_integration_exists", return_value=True)


@pytest.fixture
def mocked_kratos_info_integration_exists(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.kratos_info_integration_exists", return_value=True)


@pytest.fixture
def mocked_peer_integration_exists(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.peer_integration_exists", return_value=True)


@pytest.fixture
def all_satisfied_conditions(
    mocked_container_connectivity: MagicMock,
    mocked_secrets_is_ready: MagicMock,
    mocked_get_missing_config_keys: MagicMock,
    mocked_is_running: MagicMock,
    mocked_database_integration_exists: MagicMock,
    mocked_database_resource_is_created: MagicMock,
    mocked_migration_is_ready: MagicMock,
    mocked_openfga_integration_exists: MagicMock,
    mocked_kratos_info_integration_exists: MagicMock,
    mocked_peer_integration_exists: MagicMock,
) -> None:
    pass


# ---------------------------------------------------------------------------
# CLI / DB config / HTTP client mocks
# ---------------------------------------------------------------------------
@pytest.fixture
def mocked_cli(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.CommandLine")


@pytest.fixture
def mocked_database_config(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.DatabaseConfig")


@pytest.fixture
def mocked_requests(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.HTTPClient")
