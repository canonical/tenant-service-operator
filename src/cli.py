# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to access the tenant-service CLI."""

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from ops.model import Container
from ops.pebble import Error, ExecError

from constants import GRPC_PORT, WORKLOAD_SERVICE
from env_vars import EnvVars
from exceptions import CreateFgaModelError, MigrationCheckError, MigrationError

VERSION_REGEX = re.compile(r"App Version:\s*(?P<version>\S+)\s*$")

logger = logging.getLogger(__name__)


@dataclass
class CmdExecConfig:
    """Command Execution Config."""

    service_context: str | None = None
    environment: EnvVars = field(default_factory=dict)
    timeout: float = 20
    stdin: str | None = None


class CommandLine:
    """A class to handle command line interactions with the tenant-service."""

    def __init__(self, container: Container):
        self.container = container

    def get_service_version(self) -> str | None:
        """Get the version of the tenant-service workload.

        Returns:
            The version string, or None if it could not be determined.
        """
        cmd = ["tenant-service", "version"]
        try:
            stdout, _ = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the service version: %s", err)
            return None
        matched = VERSION_REGEX.search(stdout)
        return matched.group("version") if matched else None

    def create_openfga_model(self, url: str, api_token: str, store_id: str) -> str:
        """Create an OpenFGA authorization model.

        Args:
            url: The OpenFGA API URL.
            api_token: The OpenFGA API token.
            store_id: The OpenFGA store ID.

        Returns:
            The model ID.

        Raises:
            CreateFgaModelError: If the model creation fails or the response
                does not contain a model ID.
        """
        cmd = [
            "tenant-service",
            "create-fga-model",
            "--fga-api-url",
            url,
            "--fga-api-token",
            api_token,
            "--fga-store-id",
            store_id,
            "--format",
            "json",
        ]
        try:
            stdout, _ = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to create the OpenFGA model: %s", err)
            raise CreateFgaModelError from err
        out = json.loads(stdout)
        model_id = out.get("model_id")
        if not model_id:
            raise CreateFgaModelError("OpenFGA model creation response missing model_id")
        return model_id

    def migrate_up(self, dsn: str, timeout: float = 120) -> None:
        """Run database migrations.

        Args:
            dsn: The database connection string.
            timeout: The timeout for the migration command.

        Raises:
            MigrationError: If the migration fails.
        """
        cmd = ["tenant-service", "migrate", "up", "--dsn", dsn, "-f", "json"]
        try:
            self._run_cmd(
                cmd,
                exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE, timeout=timeout),
            )
        except Error as err:
            logger.error("Failed to migrate up the service: %s", err)
            raise MigrationError from err

    def migration_check(self, dsn: str) -> bool:
        """Check if database migrations are up to date.

        Args:
            dsn: The database connection string.

        Returns:
            True if migrations are up to date.

        Raises:
            MigrationCheckError: If the migration check fails.
        """
        cmd = ["tenant-service", "migrate", "check", "--dsn", dsn, "-f", "json"]
        try:
            stdout, stderr = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to check migration status: %s", err)
            raise MigrationCheckError("Failed to check migration status") from err
        if stderr:
            logger.error("Migration check error: %s", stderr)
            raise MigrationCheckError(f"Migration check error: {stderr}")
        out = json.loads(stdout)
        return out.get("status") == "ok"

    def create_tenant(self, name: str, token: str | None = None) -> str:
        """Create a new tenant.

        Args:
            name: The tenant name.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "create", name]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def list_tenants(
        self,
        page_size: int | None = None,
        page_token: str | None = None,
        token: str | None = None,
    ) -> str:
        """List all tenants.

        Args:
            page_size: Maximum number of results per page.
            page_token: Token to retrieve the next page of results.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "list"]
        if page_size is not None:
            cmd.extend(["--page-size", str(page_size)])
        if page_token is not None:
            cmd.extend(["--page-token", page_token])
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def delete_tenant(self, tenant_id: str, token: str | None = None) -> str:
        """Delete a tenant.

        Args:
            tenant_id: The tenant ID.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "delete", tenant_id]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def activate_tenant(self, tenant_id: str, token: str | None = None) -> str:
        """Activate a tenant.

        Args:
            tenant_id: The tenant ID.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "activate", tenant_id]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def deactivate_tenant(self, tenant_id: str, token: str | None = None) -> str:
        """Deactivate a tenant.

        Args:
            tenant_id: The tenant ID.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "deactivate", tenant_id]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def update_tenant(self, tenant_id: str, name: str, token: str | None = None) -> str:
        """Update a tenant.

        Args:
            tenant_id: The tenant ID.
            name: The new tenant name.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "update", tenant_id, name]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def list_tenant_users(
        self,
        tenant_id: str,
        page_size: int | None = None,
        page_token: str | None = None,
        token: str | None = None,
    ) -> str:
        """List users for a tenant.

        Args:
            tenant_id: The tenant ID.
            page_size: Maximum number of results per page.
            page_token: Token to retrieve the next page of results.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "users", "list", tenant_id]
        if page_size is not None:
            cmd.extend(["--page-size", str(page_size)])
        if page_token is not None:
            cmd.extend(["--page-token", page_token])
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def invite_user(self, tenant_id: str, email: str, role: str, token: str | None = None) -> str:
        """Invite a user to a tenant.

        Args:
            tenant_id: The tenant ID.
            email: The user's email address.
            role: The role to assign.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "users", "invite", tenant_id, email, role]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def provision_user(
        self, tenant_id: str, email: str, role: str, token: str | None = None
    ) -> str:
        """Provision a user for a tenant.

        Args:
            tenant_id: The tenant ID.
            email: The user's email address.
            role: The role to assign.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "users", "provision", tenant_id, email, role]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def update_user_role(
        self, tenant_id: str, user_id: str, role: str, token: str | None = None
    ) -> str:
        """Update a user's role in a tenant.

        Args:
            tenant_id: The tenant ID.
            user_id: The user ID.
            role: The new role to assign.
            token: Optional authentication token.

        Returns:
            The command output.
        """
        cmd = ["tenant-service", "tenant", "users", "update", tenant_id, user_id, "--role", role]
        cmd.extend(self._grpc_flags(token))
        stdout, _ = self._run_cmd(
            cmd,
            exec_config=CmdExecConfig(service_context=WORKLOAD_SERVICE),
        )
        return stdout

    def _grpc_flags(self, token: str | None = None) -> list[str]:
        """Build common gRPC flags for tenant/user commands.

        Args:
            token: Optional authentication token. When None a placeholder is
                used because the server requires the header even when
                authentication is disabled.

        Returns:
            A list of CLI flags.
        """
        flags = ["--grpc-endpoint", f"localhost:{GRPC_PORT}"]
        flags.extend(["--token", token or "no-token"])
        return flags

    def _run_cmd(
        self, cmd: list[str], exec_config: CmdExecConfig | None = None
    ) -> tuple[str, str]:
        """Run a command in the workload container.

        Args:
            cmd: The command to run.
            exec_config: Optional execution configuration.

        Returns:
            A tuple of (stdout, stderr).

        Raises:
            ExecError: If the command exits with a non-zero code.
        """
        if exec_config is None:
            exec_config = CmdExecConfig()
        logger.debug("Running command: %s", cmd)
        process = self.container.exec(cmd, **asdict(exec_config))
        try:
            stdout, stderr = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise
        return stdout, stderr
