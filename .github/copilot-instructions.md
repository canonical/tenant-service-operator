# Hook Service Operator - AI Coding Instructions

This repository implements a Juju Charm for the [Hook Service](https://github.com/canonical/hook-service), part of the Canonical Identity Platform. It follows the Canonical Identity Platform's standard charm architecture.

## Project Context & Architecture

- **Framework**: Python `ops` framework (Juju).
- **Target**: Kubernetes (K8s) charm.
- **Charm User**: The charm must always run as a non-root user. Do not modify `charm-user` in `charmcraft.yaml` to run as root.
- **Design Pattern**: **Physical Separation & Data Flow**.
  - **`src/charm.py`**: **Orchestrator**. Handles Juju events, initializes components, and coordinates data flow. Keep this file minimal.
  - **`src/services.py`**: **Business Logic**. Contains `WorkloadService` (app logic) and `PebbleService` (container management).
  - **`src/configs.py`**: **Data Source**. Handles charm configuration and validation.
  - **`src/integrations.py`**: **Data Source/Sink**. Wraps relation libraries and handles data transformation for integrations (e.g., `HydraHookIntegration`).
  - **`src/secret.py`**: **Data Source**. Manages Juju secrets.
  - **`src/utils.py`**: Shared utilities and decorators (e.g., `container_connectivity`, `leader_unit`).

### Data Flow Pattern
Data flows from **Sources** (Config, Relations, Secrets) -> **Orchestration** (`charm.py`) -> **Sinks** (Pebble Layer, Relation Databags).
- *Do not* pass raw relation data deep into services. Validate and structure it in `integrations.py` first.
- **Data Validation**: Use **Pydantic** models to validate data at the boundaries (e.g., in `integrations.py` or charm libraries). This ensures type safety and structural integrity before data enters the business logic.

## Critical Workflows

- **Pre-commit**: This project uses `pre-commit` to enforce standards.
  - **Formatting**: `tox -e fmt` (runs `isort` and `ruff format`). **Always run this before committing.**
  - **Linting**: `tox -e lint` (runs `ruff`, `codespell`, `mypy`).
- **Development Environment**: Use `tox devenv` to create the development virtual environment.
- **Unit Tests**: `tox -e unit`. Tests are in `tests/unit/`.
  - Mock `ops.model.Container` and external libraries.
  - **Fixtures**: Use `pytest` fixtures in `tests/unit/conftest.py` to provide common test objects like `testing.Context`, `testing.State`, and `testing.Container`. This reduces boilerplate in individual test methods.
    - Use `dataclasses.replace(default_state, ...)` to create modified states for specific test cases.
- **Integration Tests**: `tox -e integration`. Tests are in `tests/integration/`.
  - Uses `jubilant`.
- **Build**: `charmcraft pack`.
- **Library Management**: Files in `lib/charms/` are managed by `charmcraft`. Treat them as **read-only** unless they are explicitly defined and maintained by this repository (e.g., if this charm *provides* the library).

## Coding Conventions

- **Holistic Handler Pattern**: The charm uses a `_holistic_handler` method in `src/charm.py` to centralize reconciliation logic.
  - Most event handlers (e.g., `_on_config_changed`, `_on_pebble_ready`) should delegate to `_holistic_handler`.
  - This handler checks preconditions (using `NOOP_CONDITIONS` and `EVENT_DEFER_CONDITIONS`), manages secrets, updates relations, and plans the Pebble layer.
  - **Preparation Steps**: Use a loop-based approach for preparation steps that return a boolean indicating success. Use short-circuit logic:
    ```python
    can_plan = True
    for f in [self._ensure_secrets, self._ensure_hydra_relation, ...]:
        try:
            can_plan = can_plan and f()
        except CharmError:
            can_plan = False
    ```
  - **Status Management**: Unit status is handled separately in `_on_collect_status` (Juju `collect-unit-status` hook), which evaluates the overall state of the charm.
- **Event Handling**: Limit the use of `event.defer()` as much as possible. Prefer the holistic handler pattern to reconcile state based on current conditions rather than deferring events.
- **Type Hinting**: Strict typing is required. Use built-in `list`, `dict`, `tuple` (Python 3.9+) instead of `typing.List` types.
- **Logging**: Use lazy string formatting (e.g., `logger.info("key: %s", value)`) instead of f-strings to optimize performance and handling.
- **Docstrings**: Google-style docstrings for all classes and public methods.
- **Error Handling**: Use custom exceptions in `src/exceptions.py`. Catch them in `charm.py` to set unit status (e.g., `BlockedStatus`).
- **Control Flow**: Prefer **EAFP** (Easier to Ask for Forgiveness than Permission) over LBYL (Look Before You Leap). Use `try/except` blocks to handle potential failures gracefully (e.g., checking if a relation exists by accessing it inside a try block) rather than extensive pre-checks.
- **Observability**:
  - Use `charms.loki_k8s.v1.loki_push_api` for logging.
  - Use `charms.prometheus_k8s.v0.prometheus_scrape` for metrics.
  - Use `charms.tempo_coordinator_k8s.v0.tracing` for tracing.
- **Third-Party Clients**: When integrating with external APIs (e.g., Salesforce), apply **SOLID principles**. Define clear interfaces to decouple the client implementation from the charm logic, facilitating easier testing and future replacements.
- **Dependencies**:
  - Charm libraries are in `lib/charms/`.
  - Python dependencies are in `requirements.txt`.

## Configuration & Secrets

- **Sensitive Information**: Do not pass sensitive information (e.g., API keys, passwords) directly in charm config. Use **Juju Secrets**.
  - **Pattern**: The charm config should accept a Secret ID (string). The charm then retrieves the secret content using this ID.
  - **Example**: `salesforce_consumer_secret` config option takes a secret ID. The charm uses `self.model.get_secret(id=...)` to fetch the actual credentials.
- **Standard Configurations**:
  - **Proxy Configuration**: Charms that need access to the public network must include `http_proxy`, `https_proxy`, and `no_proxy`.
  - **Resource Limits**: Charms with workload containers must include `cpu` and `memory` configurations. Integrator charms do not need these.
- **Resource Management**: For charms with workload containers, use `KubernetesComputeResourcesPatch` (from `charms.observability_libs.v0.kubernetes_compute_resources_patch`) to handle `cpu` and `memory` configurations. This ensures the workload container gets the appropriate resource limits applied.

## Testing Strategy

- **Unit Tests**: Group tests logically by events (e.g., `TestInstallEvent`, `TestConfigChanged`).
  - **Framework**: Use `ops.testing` (Scenario) for unit tests. Avoid using the legacy `Harness` where possible.
  - **Scope**: Test `charm.py` logic separately from `services.py` logic. Mock dependencies to test layers in isolation.
  - **CLI Testing**: Avoid validating exact CLI command strings in unit tests as this makes tests brittle to implementation changes. Validate the *intent* or side effects in unit tests, and reserve end-to-end command execution verification for integration tests.
  - **Mocking**:
    - Mock `ops.model.Container` and external libraries.
    - **Resource Patching**: When using `KubernetesComputeResourcesPatch`, ensure it is mocked to return `ActiveStatus` (and `is_failed=(False, "")`) in unit tests. Otherwise, it may default to `WaitingStatus`, causing unrelated status assertions to fail.
- **Integration Tests**: `tox -e integration`. Tests are in `tests/integration/`.
  - Uses `jubilant`.
  - **Lifecycle Requirements**:
    - **Deploy**: Deploy app with dependencies. *Must be skippable* (e.g., via `--no-deploy`) to test against existing environments.
    - **Scale Up**: Increase unit count (e.g., to 3). Verify high availability and leader election.
    - **Business Logic**: Test core application functionality (e.g., HTTP requests, database writes).
    - **Integrations**: Test adding and removing relations (e.g., database, ingress, observability). Verify configuration updates.
    - **Actions**: Execute and verify Juju actions.
    - **Scale Down**: Decrease unit count. Verify cluster stability and data retention.
    - **Resilience**: Test failure scenarios (e.g., killing leader unit, destroying dependent charms).
    - **Upgrade**: Deploy from stable channel, then upgrade to local artifact. Verify functionality before and after.
    - **Removal**: Remove the application. *Must be skippable* (e.g., via `--keep-models`) for debugging.

## Integration Points

- **Hydra**: Provides `hydra-token-hook` relation.
- **Traefik**: Consumes `ingress` relation for external access.
- **Observability**: Integrates with COS Lite bundle (Loki, Prometheus, Grafana, Tempo).

## Example: Adding a new relation
1. Add library to `lib/`.
2. Define wrapper class in `src/integrations.py`.
3. Instantiate in `src/charm.py` `__init__`.
4. Handle events in `src/charm.py` (e.g., `self.framework.observe(self.relation.on.ready, self._on_relation_ready)`).

## Debugging Deployments

When debugging deployment issues, follow this structured approach. **Note**: The MCP server tools are **MANDATORY** for their integration. Do not use the standard CLI commands unless the MCP server is unavailable.

1. **Check Model Status**: Use the MCP server (`get_status`) to identify blocked or waiting units.
   - Look for status messages indicating missing dependencies or check failures (e.g., "Migration check failed").
2. **Inspect Juju Logs**: Use the MCP server (`get_debug_log`) to find specific error messages from the charm code.
   - Look for Python exceptions or non-zero exit codes from subprocess calls.
3. **Inspect Workload Logs**: Use the MCP server (`get_workload_logs`) to check the application's standard output/error.
   - This helps identify application startup issues that the charm might not catch immediately.
4. **Verify Workload Environment**: Use `kubectl exec` to run commands inside the container.
   - Verify the application version (`<app-binary> version`).
   - Verify available commands (`<app-binary> --help`).
   - Check for missing files or permissions.

## Continuous Improvement

- **Instruction Maintenance**: As you work on the codebase, if you identify new patterns, best practices, or recurring issues that are not covered here, **you must update this file**. This ensures that the instructions remain relevant and helpful for future tasks.
