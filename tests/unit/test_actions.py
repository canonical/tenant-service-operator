# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops import testing
from unit.conftest import create_state


class TestCreateTenantAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.create_tenant.return_value = "Tenant created: test (ID: 123)"
        state = create_state()
        context.run(context.on.action("create-tenant", params={"name": "test"}), state)
        mocked_cli.return_value.create_tenant.assert_called_once_with(name="test")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.create_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to create tenant"):
            context.run(context.on.action("create-tenant", params={"name": "test"}), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("create-tenant", params={"name": "test"}), state)


class TestListTenantsAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.list_tenants.return_value = "ID  NAME"
        state = create_state()
        context.run(context.on.action("list-tenants"), state)
        mocked_cli.return_value.list_tenants.assert_called_once()

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.list_tenants.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to list tenants"):
            context.run(context.on.action("list-tenants"), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("list-tenants"), state)


class TestDeleteTenantAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.delete_tenant.return_value = "Tenant deleted"
        state = create_state()
        context.run(context.on.action("delete-tenant", params={"tenant-id": "abc"}), state)
        mocked_cli.return_value.delete_tenant.assert_called_once_with(tenant_id="abc")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.delete_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to delete tenant"):
            context.run(context.on.action("delete-tenant", params={"tenant-id": "abc"}), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("delete-tenant", params={"tenant-id": "abc"}), state)


class TestActivateTenantAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.activate_tenant.return_value = "Tenant activated"
        state = create_state()
        context.run(context.on.action("activate-tenant", params={"tenant-id": "abc"}), state)
        mocked_cli.return_value.activate_tenant.assert_called_once_with(tenant_id="abc")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.activate_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to activate tenant"):
            context.run(context.on.action("activate-tenant", params={"tenant-id": "abc"}), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("activate-tenant", params={"tenant-id": "abc"}), state)


class TestDeactivateTenantAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.deactivate_tenant.return_value = "Tenant deactivated"
        state = create_state()
        context.run(context.on.action("deactivate-tenant", params={"tenant-id": "abc"}), state)
        mocked_cli.return_value.deactivate_tenant.assert_called_once_with(tenant_id="abc")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.deactivate_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to deactivate tenant"):
            context.run(context.on.action("deactivate-tenant", params={"tenant-id": "abc"}), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("deactivate-tenant", params={"tenant-id": "abc"}), state)


class TestUpdateTenantAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.update_tenant.return_value = "Tenant updated"
        state = create_state()
        context.run(
            context.on.action("update-tenant", params={"tenant-id": "abc", "name": "new"}),
            state,
        )
        mocked_cli.return_value.update_tenant.assert_called_once_with(tenant_id="abc", name="new")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.update_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to update tenant"):
            context.run(
                context.on.action("update-tenant", params={"tenant-id": "abc", "name": "new"}),
                state,
            )

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(
                context.on.action("update-tenant", params={"tenant-id": "abc", "name": "new"}),
                state,
            )


class TestListTenantUsersAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.list_tenant_users.return_value = "USER_ID EMAIL ROLE"
        state = create_state()
        context.run(context.on.action("list-tenant-users", params={"tenant-id": "abc"}), state)
        mocked_cli.return_value.list_tenant_users.assert_called_once_with(tenant_id="abc")

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.list_tenant_users.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to list tenant users"):
            context.run(context.on.action("list-tenant-users", params={"tenant-id": "abc"}), state)

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("list-tenant-users", params={"tenant-id": "abc"}), state)


class TestInviteUserAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.invite_user.return_value = "User invited"
        state = create_state()
        context.run(
            context.on.action(
                "invite-user", params={"tenant-id": "abc", "email": "a@b.c", "role": "admin"}
            ),
            state,
        )
        mocked_cli.return_value.invite_user.assert_called_once_with(
            tenant_id="abc", email="a@b.c", role="admin"
        )

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.invite_user.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to invite user"):
            context.run(
                context.on.action(
                    "invite-user",
                    params={"tenant-id": "abc", "email": "a@b.c", "role": "admin"},
                ),
                state,
            )

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(
                context.on.action(
                    "invite-user",
                    params={"tenant-id": "abc", "email": "a@b.c", "role": "admin"},
                ),
                state,
            )


class TestProvisionUserAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.provision_user.return_value = "User provisioned"
        state = create_state()
        context.run(
            context.on.action(
                "provision-user",
                params={"tenant-id": "abc", "email": "a@b.c", "role": "member"},
            ),
            state,
        )
        mocked_cli.return_value.provision_user.assert_called_once_with(
            tenant_id="abc", email="a@b.c", role="member"
        )

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.provision_user.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to provision user"):
            context.run(
                context.on.action(
                    "provision-user",
                    params={"tenant-id": "abc", "email": "a@b.c", "role": "member"},
                ),
                state,
            )

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(
                context.on.action(
                    "provision-user",
                    params={"tenant-id": "abc", "email": "a@b.c", "role": "member"},
                ),
                state,
            )


class TestUpdateUserRoleAction:
    def test_success(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.update_user_role.return_value = "Role updated"
        state = create_state()
        context.run(
            context.on.action(
                "update-user-role",
                params={"tenant-id": "abc", "user-id": "u1", "role": "admin"},
            ),
            state,
        )
        mocked_cli.return_value.update_user_role.assert_called_once_with(
            tenant_id="abc", user_id="u1", role="admin"
        )

    def test_failure(
        self,
        context: testing.Context,
        mocked_cli: MagicMock,
    ) -> None:
        mocked_cli.return_value.update_user_role.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to update user role"):
            context.run(
                context.on.action(
                    "update-user-role",
                    params={"tenant-id": "abc", "user-id": "u1", "role": "admin"},
                ),
                state,
            )

    def test_container_not_ready(
        self,
        context: testing.Context,
    ) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(
                context.on.action(
                    "update-user-role",
                    params={"tenant-id": "abc", "user-id": "u1", "role": "admin"},
                ),
                state,
            )
