# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, create_autospec

import pytest
from ops.model import Container
from ops.pebble import ExecError

from cli import CommandLine
from exceptions import CreateFgaStoreError, MigrationCheckError, MigrationError


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def cli(mocked_container: MagicMock) -> CommandLine:
    return CommandLine(mocked_container)


class TestGetServiceVersion:
    def test_success(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("App Version: 1.0.0", "")
        mocked_container.exec.return_value = process

        result = cli.get_service_version()

        assert result == "1.0.0"

    def test_failure(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        mocked_container.exec.side_effect = ExecError(["tenant-service", "version"], 1, "", "")

        result = cli.get_service_version()

        assert result is None

    def test_no_match(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("some unexpected output", "")
        mocked_container.exec.return_value = process

        result = cli.get_service_version()

        assert result is None


class TestMigrateUp:
    def test_success(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("", "")
        mocked_container.exec.return_value = process

        cli.migrate_up(dsn="postgres://user:pass@host/db")

        mocked_container.exec.assert_called_once()
        call_args = mocked_container.exec.call_args[0][0]
        assert "migrate" in call_args
        assert "up" in call_args
        assert "postgres://user:pass@host/db" in call_args

    def test_failure(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.side_effect = ExecError(["tenant-service", "migrate", "up"], 1, "", "")
        mocked_container.exec.return_value = process

        with pytest.raises(MigrationError):
            cli.migrate_up(dsn="postgres://user:pass@host/db")


class TestMigrationCheck:
    def test_ok(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = (json.dumps({"status": "ok"}), "")
        mocked_container.exec.return_value = process

        result = cli.migration_check(dsn="postgres://user:pass@host/db")

        assert result is True

    def test_not_ok(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = (json.dumps({"status": "pending"}), "")
        mocked_container.exec.return_value = process

        result = cli.migration_check(dsn="postgres://user:pass@host/db")

        assert result is False

    def test_failure(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.side_effect = ExecError(
            ["tenant-service", "migrate", "check"], 1, "", ""
        )
        mocked_container.exec.return_value = process

        with pytest.raises(MigrationCheckError):
            cli.migration_check(dsn="postgres://user:pass@host/db")

    def test_stderr(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = (json.dumps({"status": "ok"}), "some warning")
        mocked_container.exec.return_value = process

        with pytest.raises(MigrationCheckError, match="some warning"):
            cli.migration_check(dsn="postgres://user:pass@host/db")


class TestCreateOpenfgaModel:
    def test_success(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        model_id = "01HT27W9Y00000000000000000"
        process = MagicMock()
        process.wait_output.return_value = (json.dumps({"model_id": model_id}), "")
        mocked_container.exec.return_value = process

        result = cli.create_openfga_model(
            url="http://openfga:8080", api_token="token", store_id="store-1"
        )

        assert result == model_id
        call_args = mocked_container.exec.call_args[0][0]
        assert "create-fga-model" in call_args
        assert "--fga-api-url" in call_args
        assert "http://openfga:8080" in call_args
        assert "--fga-api-token" in call_args
        assert "token" in call_args
        assert "--fga-store-id" in call_args
        assert "store-1" in call_args

    def test_failure(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.side_effect = ExecError(
            ["tenant-service", "create-fga-model"], 1, "", ""
        )
        mocked_container.exec.return_value = process

        with pytest.raises(CreateFgaStoreError):
            cli.create_openfga_model(
                url="http://openfga:8080", api_token="token", store_id="store-1"
            )


class TestTenantCommands:
    def test_create_tenant(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant created: test (ID: 123)", "")
        mocked_container.exec.return_value = process

        result = cli.create_tenant(name="test")

        assert result == "Tenant created: test (ID: 123)"
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "create" in call_args
        assert "test" in call_args

    def test_create_tenant_with_token(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant created", "")
        mocked_container.exec.return_value = process

        result = cli.create_tenant(name="test", token="bearer-abc")

        assert result == "Tenant created"
        call_args = mocked_container.exec.call_args[0][0]
        assert "--token" in call_args
        assert "bearer-abc" in call_args

    def test_list_tenants(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("ID  NAME\n1  tenant-a", "")
        mocked_container.exec.return_value = process

        result = cli.list_tenants()

        assert "tenant-a" in result
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "list" in call_args

    def test_delete_tenant(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant deleted", "")
        mocked_container.exec.return_value = process

        result = cli.delete_tenant(tenant_id="abc-123")

        assert result == "Tenant deleted"
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "delete" in call_args
        assert "abc-123" in call_args

    def test_activate_tenant(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant activated", "")
        mocked_container.exec.return_value = process

        result = cli.activate_tenant(tenant_id="abc-123")

        assert result == "Tenant activated"
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "activate" in call_args

    def test_deactivate_tenant(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant deactivated", "")
        mocked_container.exec.return_value = process

        result = cli.deactivate_tenant(tenant_id="abc-123")

        assert result == "Tenant deactivated"
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "deactivate" in call_args

    def test_update_tenant(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Tenant updated", "")
        mocked_container.exec.return_value = process

        result = cli.update_tenant(tenant_id="abc-123", name="new-name")

        assert result == "Tenant updated"
        call_args = mocked_container.exec.call_args[0][0]
        assert "tenant" in call_args
        assert "update" in call_args
        assert "abc-123" in call_args
        assert "--name" in call_args
        assert "new-name" in call_args


class TestUserCommands:
    def test_list_tenant_users(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("USER_ID  EMAIL  ROLE", "")
        mocked_container.exec.return_value = process

        result = cli.list_tenant_users(tenant_id="abc-123")

        assert "USER_ID" in result
        call_args = mocked_container.exec.call_args[0][0]
        assert "users" in call_args
        assert "list" in call_args
        assert "abc-123" in call_args

    def test_invite_user(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("User invited", "")
        mocked_container.exec.return_value = process

        result = cli.invite_user(tenant_id="abc-123", email="a@b.c", role="admin")

        assert result == "User invited"
        call_args = mocked_container.exec.call_args[0][0]
        assert "users" in call_args
        assert "invite" in call_args
        assert "abc-123" in call_args
        assert "a@b.c" in call_args
        assert "admin" in call_args

    def test_provision_user(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("User provisioned", "")
        mocked_container.exec.return_value = process

        result = cli.provision_user(tenant_id="abc-123", email="a@b.c", role="member")

        assert result == "User provisioned"
        call_args = mocked_container.exec.call_args[0][0]
        assert "users" in call_args
        assert "provision" in call_args
        assert "abc-123" in call_args
        assert "a@b.c" in call_args
        assert "member" in call_args

    def test_update_user_role(self, cli: CommandLine, mocked_container: MagicMock) -> None:
        process = MagicMock()
        process.wait_output.return_value = ("Role updated", "")
        mocked_container.exec.return_value = process

        result = cli.update_user_role(tenant_id="abc-123", user_id="u1", role="admin")

        assert result == "Role updated"
        call_args = mocked_container.exec.call_args[0][0]
        assert "users" in call_args
        assert "update" in call_args
        assert "abc-123" in call_args
        assert "u1" in call_args
        assert "--role" in call_args
        assert "admin" in call_args
