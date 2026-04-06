---
description: "Use when writing or modifying unit tests, integration tests, test fixtures, or conftest files for the charm. Covers test file structure, fixture patterns, ops.testing (Scenario) usage, and test organization."
applyTo: "tests/**"
---

# Testing Guidelines

## Reference Implementation

The pattern reference is **hydra-operator** and **kratos-operator**, NOT hook-service-operator.

## File Structure

One file per concern:

| File | Scope |
|------|-------|
| `test_charm.py` | Lifecycle events, holistic handler, collect-status, relation events |
| `test_actions.py` | Juju action handlers (tenant CRUD, user management) |
| `test_integrations.py` | Integration wrapper classes tested in isolation |
| `test_cli.py` | CLI wrapper methods with mocked Container |
| `test_configs.py` | CharmConfig validation and env var output |

## Unit Tests (`tests/unit/`)

- **Framework**: `ops.testing` (Scenario). Do not use legacy `Harness`.
- **State factory**: Use `create_state()` — a **module-level factory function** in `conftest.py` (NOT a fixture). Import it in test files.
- **Do NOT** use `dataclasses.replace()` or `replace_state()` to modify states. Always create a fresh state via `create_state()`.
- Group tests in classes by event or feature (e.g., `TestPebbleReadyEvent`, `TestCollectStatusEvent`).

### `create_state()` Factory Pattern

`create_state()` lives in `conftest.py` as a plain function. Test files import it directly:

```python
from unit.conftest import create_state

# Minimal state (leader=True, can_connect=True, no relations)
state = create_state()

# Custom state
state = create_state(
    leader=False,
    relations=[database_relation, peer_relation],
    secrets=[api_token_secret],
    config={"authorization_enabled": True},
    can_connect=False,
)
```

Supported kwargs: `leader`, `secrets`, `relations`, `containers`, `config`, `can_connect`, `workload_version`. The factory builds a complete `testing.State` with sensible defaults (leader=True, can_connect=True, default execs for CLI commands).

### Mocking Rules

Autouse fixtures in `conftest.py` (apply to every test automatically):

- **`mocked_k8s_resource_patch`** — Mocks `KubernetesComputeResourcesPatch` using two fixtures: `mocked_resource_patch` (patches `ResourcePatcher`) + `mocked_k8s_resource_patch` (patches via `mocker.patch.multiple`).
- **`mocked_openfga_integration`** — Mocks `OpenFGAIntegration.is_store_ready` to return `True`.
- **`mocked_subprocess_run`** — Mocks `subprocess.run` to prevent real cert updates.
- For `collect-unit-status` tests, use the `all_satisfied_conditions` fixture that mocks all condition functions to return satisfied values.

### Action Test Pattern

Each action test class should have at minimum:
- `test_success` — happy path, assert CLI method called with correct args
- `test_failure` — CLI raises Exception, assert action fails with `testing.ActionFailed`
- `test_container_not_ready` — disconnected container, assert action fails with `testing.ActionFailed`

**Important**: Use `pytest.raises(testing.ActionFailed, ...)` for action failures, NOT generic `Exception`.

```python
from unit.conftest import create_state


class TestCreateTenantAction:
    def test_success(self, context: testing.Context, mocked_cli: MagicMock) -> None:
        mocked_cli.return_value.create_tenant.return_value = "Tenant created"
        state = create_state()
        context.run(context.on.action("create-tenant", params={"name": "test"}), state)
        mocked_cli.return_value.create_tenant.assert_called_once_with(name="test")

    def test_failure(self, context: testing.Context, mocked_cli: MagicMock) -> None:
        mocked_cli.return_value.create_tenant.side_effect = Exception("fail")
        state = create_state()
        with pytest.raises(testing.ActionFailed, match="Failed to create tenant"):
            context.run(context.on.action("create-tenant", params={"name": "test"}), state)

    def test_container_not_ready(self, context: testing.Context) -> None:
        state = create_state(can_connect=False)
        with pytest.raises(testing.ActionFailed, match="Workload container is not ready"):
            context.run(context.on.action("create-tenant", params={"name": "test"}), state)
```

### Integration Wrapper Test Pattern

Test wrappers in isolation using `create_autospec()` for library objects:
- `load()` classmethods: test with/without relation data
- `to_env_vars()`: verify correct env var keys and values
- `is_ready()` / `is_store_ready()`: test true/false paths

These are pure mock tests — no `create_state()` needed.

## Integration Tests (`tests/integration/`)

- **Framework**: `jubilant` library.
- **Lifecycle order**: deploy → health check → scale up → actions → remove/re-add integrations → scale down → removal.
- **Skippable**: Deploy (`--no-deploy`) and removal (`--keep-models`) must be skippable.
- Use `conftest.py` for model/charm fixtures, `constants.py` for app names, `utils.py` for helpers.
