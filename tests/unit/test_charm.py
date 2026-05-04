# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import ops
import pytest
from ops import StatusBase, testing
from ops.testing import ActionFailed
from pytest_mock import MockerFixture
from unit.conftest import create_state

from constants import (
    KRATOS_INFO_INTEGRATION_NAME,
    OPENFGA_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import MigrationCheckError, MigrationError


class TestPebbleReadyEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        container: testing.Container,
        mocked_open_port: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
        mocked_workload_service_version: MagicMock,
        all_satisfied_conditions: None,
    ) -> None:
        state = create_state()

        state_out = context.run(context.on.pebble_ready(container), state)

        assert state_out.unit_status == testing.ActiveStatus()
        mocked_open_port.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()
        assert state_out.workload_version == mocked_workload_service_version.return_value


class TestAuthn:
    def test_when_oauth_relation_exists(
        self,
        context: testing.Context,
        container: testing.Container,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test that correct env vars are set when OAuth relation exists."""
        config = {
            "authn_allowed_subjects": "user1, user2",
            "authn_allowed_scope": "email",
        }

        client_secret = testing.Secret(
            id="tenant-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        state = create_state(
            relations=[
                oauth_relation,
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            config=config,
            secrets=[client_secret, api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.pebble_ready(container), state)

        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers["tenant-service"]
        service = layer.services["tenant-service"]
        env = service.environment

        assert env["AUTHENTICATION_ENABLED"]
        assert env["AUTHENTICATION_ISSUER"] == "https://hydra.example.com"
        subjects = env["AUTHENTICATION_ALLOWED_SUBJECTS"].split(",")
        assert "tenant-service-client-id" in subjects
        assert "user1" in subjects
        assert "user2" in subjects
        assert env["AUTHENTICATION_REQUIRED_SCOPE"] == "email"
        assert env["AUTHENTICATION_JWKS_URL"] == ""

    def test_when_manual_config_exists(
        self,
        context: testing.Context,
        container: testing.Container,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
    ) -> None:
        """Test that correct env vars are set when manual config is provided."""
        config = {
            "authn_issuer": "https://manual.example.com",
            "authn_jwks_url": "https://manual.example.com/jwks",
            "authn_allowed_subjects": "manual_user",
            "authn_allowed_scope": "profile",
        }
        state = create_state(
            relations=[
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            config=config,
            secrets=[api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.pebble_ready(container), state)

        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers["tenant-service"]
        service = layer.services["tenant-service"]
        env = service.environment

        assert env["AUTHENTICATION_ENABLED"]
        assert env["AUTHENTICATION_ISSUER"] == "https://manual.example.com"
        assert env["AUTHENTICATION_JWKS_URL"] == "https://manual.example.com/jwks"
        assert env["AUTHENTICATION_ALLOWED_SUBJECTS"] == "manual_user"
        assert env["AUTHENTICATION_REQUIRED_SCOPE"] == "profile"


class TestConfigChangedEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        all_satisfied_conditions: None,
    ) -> None:
        state = create_state()

        state_out = context.run(context.on.config_changed(), state)

        assert state_out.unit_status == testing.ActiveStatus()
        mocked_charm_holistic_handler.assert_called_once()


class TestIngressReadyEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        internal_route_integration: testing.Relation,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
    ) -> None:
        state = create_state(
            relations=[
                internal_route_integration,
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.relation_joined(internal_route_integration), state)

        assert state_out.unit_status == testing.ActiveStatus()


class TestIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        context: testing.Context,
        internal_route_integration: testing.Relation,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
    ) -> None:
        state = create_state(
            relations=[
                internal_route_integration,
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.relation_broken(internal_route_integration), state)

        assert state_out.unit_status == testing.ActiveStatus()


class TestHolisticHandler:
    def test_when_container_not_connected(
        self,
        context: testing.Context,
        all_satisfied_conditions: None,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("charm.container_connectivity", return_value=False)
        state = create_state(can_connect=False)

        state_out = context.run(context.on.config_changed(), state)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_all_conditions_satisfied(
        self,
        context: testing.Context,
        internal_route_integration: testing.Relation,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        api_token: str,
        openfga_model_id: str,
    ) -> None:
        state = create_state(
            relations=[
                internal_route_integration,
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.config_changed(), state)

        layer = state_out.get_container("tenant-service").layers["tenant-service"]
        assert state_out.unit_status == testing.ActiveStatus()
        env = layer.services.get("tenant-service").environment
        assert env["WEBHOOKS_API_TOKEN"] == api_token
        assert env["KRATOS_ADMIN_URL"] == "http://kratos-admin:4434"
        assert env["INVITATION_LIFETIME"] == "24h"
        assert env["GRPC_PORT"] == str(50051)
        assert env["PORT"] == str(8080)
        assert env["AUTHORIZATION_ENABLED"] is True
        assert env["DSN"].startswith("postgres://")
        assert env["OPENFGA_API_HOST"] == "openfga:8080"
        assert env["OPENFGA_API_SCHEME"] == "http"
        assert env["OPENFGA_API_TOKEN"] == openfga_secret.tracked_content["token"]
        assert env["OPENFGA_STORE_ID"] == "some-store-id"

    def test_migration_needed_not_leader(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False

        state = create_state(
            leader=False,
            relations=[
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        context.run(context.on.config_changed(), state)

        mocked_cli.return_value.migrate_up.assert_not_called()

    def test_migration_needed_leader_success(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False

        state = create_state(
            relations=[
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        context.run(context.on.config_changed(), state)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_needed_leader_failure(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.return_value = False
        mocked_cli.return_value.migrate_up.side_effect = MigrationError("failed")

        state = create_state(
            relations=[
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        context.run(context.on.config_changed(), state)

        mocked_cli.return_value.migrate_up.assert_called_once()

    def test_migration_check_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.migration_check.side_effect = MigrationCheckError("failed")

        state = create_state(relations=[])

        context.run(context.on.config_changed(), state)

        mocked_cli.return_value.migrate_up.assert_not_called()


class TestCollectStatusEvent:
    def test_when_all_condition_satisfied(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        state = create_state()

        state_out = context.run(context.on.collect_unit_status(), state)

        assert state_out.unit_status == testing.ActiveStatus()

    def test_status_when_valid_oauth_relation(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test that status is Active when OAuth relation is valid and no conflicting config."""
        client_secret = testing.Secret(
            id="tenant-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )
        state = create_state(
            relations=[oauth_relation],
            secrets=[client_secret],
        )

        state_out = context.run(context.on.collect_unit_status(), state)

        assert state_out.unit_status == testing.ActiveStatus()

    def test_status_when_conflicting_config(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        oauth_relation: testing.Relation,
    ) -> None:
        """Test behavior when both relation and manual issuer/jwks config are present."""
        client_secret = testing.Secret(
            id="tenant-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        config = {
            "authn_issuer": "https://conflict.example.com",
        }
        state = create_state(
            relations=[oauth_relation],
            config=config,
            secrets=[client_secret],
        )

        state_out = context.run(context.on.collect_unit_status(), state)

        assert state_out.unit_status == testing.ActiveStatus(
            "Ignoring authentication config due to OAuth integration"
        )

    def test_status_when_partial_manual_config(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        """Test BlockedStatus when manual config is missing issuer."""
        config = {
            "authn_allowed_subjects": "user1",
        }
        state = create_state(config=config)

        state_out = context.run(context.on.collect_unit_status(), state)

        assert isinstance(state_out.unit_status, testing.BlockedStatus)

    @pytest.mark.parametrize(
        "condition, condition_value, status, message, leader",
        [
            (
                "container_connectivity",
                False,
                testing.WaitingStatus,
                "Container is not connected yet",
                True,
            ),
            (
                "WorkloadService.is_failing",
                True,
                testing.BlockedStatus,
                f"Failed to start the service, please check the "
                f"{WORKLOAD_CONTAINER} container logs",
                True,
            ),
            (
                "database_resource_is_created",
                False,
                testing.WaitingStatus,
                "Waiting for database creation",
                True,
            ),
            (
                "migration_is_ready",
                MigrationCheckError("failed"),
                testing.BlockedStatus,
                "Migration check failed: failed",
                True,
            ),
            (
                "migration_is_ready",
                False,
                testing.WaitingStatus,
                "Waiting for database migration",
                True,
            ),
            (
                "migration_is_ready",
                False,
                testing.WaitingStatus,
                "Waiting for leader unit to run the migration",
                False,
            ),
            (
                "kratos_info_integration_exists",
                False,
                testing.BlockedStatus,
                f"Missing integration {KRATOS_INFO_INTEGRATION_NAME}",
                True,
            ),
        ],
        ids=[
            "container_not_connected",
            "workload_service_failing",
            "database_resource_not_created",
            "migration_check_error",
            "migration_not_ready",
            "not_leader_waiting_for_migration",
            "kratos_info_missing",
        ],
    )
    def test_when_a_condition_failed(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        condition: str,
        condition_value: bool | Exception,
        status: type[StatusBase],
        message: str,
        leader: bool,
    ) -> None:
        state = create_state(leader=leader)

        patch_kwargs: dict[str, Any] = {}
        if isinstance(condition_value, Exception):
            patch_kwargs["side_effect"] = condition_value
        else:
            patch_kwargs["return_value"] = condition_value

        with patch(f"charm.{condition}", **patch_kwargs):
            state_out = context.run(context.on.collect_unit_status(), state)

        assert isinstance(state_out.unit_status, status)
        assert state_out.unit_status.message == message

    def test_openfga_missing_when_authorization_enabled(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        """Test that OpenFGA missing blocks when authorization_enabled=true."""
        state = create_state(config={"authorization_enabled": True})

        with patch("charm.openfga_integration_exists", return_value=False):
            state_out = context.run(context.on.collect_unit_status(), state)

        assert isinstance(state_out.unit_status, testing.BlockedStatus)
        assert state_out.unit_status.message == f"Missing integration {OPENFGA_INTEGRATION_NAME}"

    def test_openfga_missing_when_authorization_disabled(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
    ) -> None:
        """Test that OpenFGA missing does NOT block when authorization_enabled=false."""
        state = create_state(config={"authorization_enabled": False})

        with patch("charm.openfga_integration_exists", return_value=False):
            state_out = context.run(context.on.collect_unit_status(), state)

        assert state_out.unit_status == testing.ActiveStatus()

    def test_openfga_store_not_ready_when_authorization_enabled(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        mocked_openfga_integration: MagicMock,
    ) -> None:
        """Test that OpenFGA store not ready blocks when authorization_enabled=true."""
        mocked_openfga_integration.return_value = False
        state = create_state(config={"authorization_enabled": True})

        state_out = context.run(context.on.collect_unit_status(), state)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        assert state_out.unit_status.message == "Waiting for openfga store to be created"

    def test_openfga_store_not_ready_when_authorization_disabled(
        self,
        context: testing.Context,
        all_satisfied_conditions: MagicMock,
        mocked_openfga_integration: MagicMock,
    ) -> None:
        """Test that OpenFGA store not ready does NOT block when authorization_enabled=false."""
        mocked_openfga_integration.return_value = False
        state = create_state(config={"authorization_enabled": False})

        state_out = context.run(context.on.collect_unit_status(), state)

        assert state_out.unit_status == testing.ActiveStatus()


class TestDatabaseEvents:
    def test_on_database_created(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        database_relation: testing.Relation,
    ) -> None:
        state = create_state(relations=[database_relation])

        context.run(context.on.relation_changed(database_relation), state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_database_integration_broken(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
        mocker: MockerFixture,
    ) -> None:
        """Test that database relation-broken stops the workload service."""
        mock_stop = mocker.patch("ops.model.Container.stop")
        state = create_state(relations=[database_relation])

        context.run(context.on.relation_broken(database_relation), state)

        mock_stop.assert_called_once_with(WORKLOAD_CONTAINER)

    def test_on_database_integration_broken_container_not_connected(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
    ) -> None:
        """Test that database relation-broken handles disconnected container gracefully."""
        state = create_state(relations=[database_relation], can_connect=False)

        # Should not raise
        context.run(context.on.relation_broken(database_relation), state)


class TestOpenFGAEvents:
    def test_on_openfga_store_created(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
    ) -> None:
        state = create_state(relations=[openfga_relation])

        context.run(context.on.relation_changed(openfga_relation), state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_openfga_store_removed(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
    ) -> None:
        state = create_state(relations=[openfga_relation])

        context.run(context.on.relation_departed(openfga_relation), state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_openfga_store_removed_leader(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        openfga_relation: testing.Relation,
        peer_relation: testing.PeerRelation,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        version = mocked_workload_service_version.return_value

        state = create_state(relations=[openfga_relation, peer_relation])

        state_out = context.run(context.on.relation_departed(openfga_relation), state)

        mocked_charm_holistic_handler.assert_called_once()
        peer_rel_out = state_out.get_relation(peer_relation.id)
        assert version not in peer_rel_out.local_app_data


class TestGetAccessTokenAction:
    def test_when_oauth_integration_missing(
        self,
        context: testing.Context,
    ) -> None:
        """Test action failure when integration is missing."""
        state = create_state()

        with pytest.raises(ActionFailed, match="OAuth integration is not ready"):
            context.run(context.on.action("get-access-token"), state)

    def test_when_success(
        self,
        context: testing.Context,
        oauth_relation: testing.Relation,
        mocked_requests: MagicMock,
    ) -> None:
        """Test successful token retrieval."""
        mock_client = mocked_requests.return_value.__enter__.return_value
        mock_client.get_access_token.return_value = "my-token"

        client_secret = testing.Secret(
            id="tenant-service-client-secret",
            tracked_content={"secret": "supersecret"},
            latest_content={"secret": "supersecret"},
        )

        state = create_state(
            relations=[oauth_relation],
            secrets=[client_secret],
        )

        context.run(context.on.action("get-access-token"), state)

        mock_client.get_access_token.assert_called_with(
            client_id="tenant-service-client-id",
            client_secret="supersecret",
        )


class TestCertificateEvents:
    def test_on_certificate_changed(
        self,
        context: testing.Context,
        certificate_transfer_relation: testing.Relation,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        mocked_subprocess_run: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        mock_path = mocker.patch("charm.LOCAL_CHARM_CERTIFICATES_FILE")
        mock_path.exists.return_value = False
        mock_path.parent.mkdir.return_value = None

        mock_tls = mocker.patch("charm.TLSCertificates")
        mock_tls.load.return_value.ca_bundle = "some-ca-cert"

        state = create_state(
            relations=[
                certificate_transfer_relation,
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        context.run(context.on.relation_changed(certificate_transfer_relation), state)

        mock_path.write_text.assert_called_with("some-ca-cert")
        mocked_subprocess_run.assert_called()


class TestKratosInfoEvents:
    def test_on_kratos_info_changed(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        kratos_info_relation: testing.Relation,
    ) -> None:
        state = create_state(relations=[kratos_info_relation])

        context.run(context.on.relation_changed(kratos_info_relation), state)

        mocked_charm_holistic_handler.assert_called_once()

    def test_on_kratos_info_broken(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
        kratos_info_relation: testing.Relation,
    ) -> None:
        state = create_state(relations=[kratos_info_relation])

        context.run(context.on.relation_broken(kratos_info_relation), state)

        mocked_charm_holistic_handler.assert_called_once()


class TestKratosLoginWebhookEvents:
    def test_on_kratos_login_webhook_ready(
        self,
        context: testing.Context,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        kratos_login_webhook_relation = testing.Relation(
            endpoint="kratos-login-webhook",
            interface="kratos_login_webhook",
            remote_app_name="kratos",
        )
        state = create_state(relations=[kratos_login_webhook_relation])

        context.run(context.on.relation_created(kratos_login_webhook_relation), state)

        mocked_charm_holistic_handler.assert_called_once()


class TestTLSFailure:
    def test_ensure_tls_subprocess_failure_blocks_plan(
        self,
        context: testing.Context,
        database_relation: testing.Relation,
        openfga_relation: testing.Relation,
        openfga_secret: testing.Secret,
        peer_relation: testing.PeerRelation,
        kratos_info_relation: testing.Relation,
        api_token_secret: testing.Secret,
        mocked_subprocess_run: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        """Test that TLS CA update failure prevents pebble plan (returns False)."""
        mock_path = mocker.patch("charm.LOCAL_CHARM_CERTIFICATES_FILE")
        mock_path.exists.return_value = False
        mock_path.parent.mkdir.return_value = None

        mock_tls = mocker.patch("charm.TLSCertificates")
        mock_tls.load.return_value.ca_bundle = "new-ca-cert"

        mocked_subprocess_run.side_effect = subprocess.CalledProcessError(
            1, "update-ca-certificates"
        )

        state = create_state(
            relations=[
                database_relation,
                openfga_relation,
                peer_relation,
                kratos_info_relation,
            ],
            secrets=[api_token_secret, openfga_secret],
        )

        state_out = context.run(context.on.config_changed(), state)

        mock_path.unlink.assert_called_with(missing_ok=True)
        # Service should NOT be planned since _ensure_tls returns False
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        assert "tenant-service" not in container_out.layers


class TestSecretMissing:
    def test_api_token_missing_raises_value_error(self) -> None:
        """Test that accessing api_token without secret raises ValueError."""
        from unittest.mock import MagicMock as MockModel

        from secret import Secrets

        mock_model = MockModel()
        mock_model.get_secret.side_effect = ops.SecretNotFoundError("not found")
        secrets = Secrets(mock_model)
        with pytest.raises(ValueError, match="API token secret is not available"):
            _ = secrets.api_token

    def test_to_env_vars_with_missing_secret_raises(self) -> None:
        """Test that to_env_vars raises when api_token is missing."""
        from unittest.mock import MagicMock as MockModel

        from secret import Secrets

        mock_model = MockModel()
        mock_model.get_secret.side_effect = ops.SecretNotFoundError("not found")
        secrets = Secrets(mock_model)
        with pytest.raises(ValueError, match="API token secret is not available"):
            secrets.to_env_vars()
