# Tenant Service Operator - AI Coding Instructions

This repository implements a Juju Charm for the [Tenant Service](https://github.com/canonical/tenant-service), part of the Canonical Identity Platform. It follows the Canonical Identity Platform's standard charm architecture.

## Project Context & Architecture

- **Framework**: Python `ops` framework (Juju), Kubernetes charm.
- **Charm User**: Must always run as non-root. Do not modify `charm-user` in `charmcraft.yaml`.
- **Workload**: Go application exposing HTTP (:8080) and gRPC (:50051) APIs for multi-tenant management.
- **Specification**: See `docs/spec/CHARM_SPECIFICATION.md` for the full design.
- **ADRs**: Architectural decisions are recorded in `docs/adr/`.

### Design Pattern: Physical Separation & Data Flow

- **`src/charm.py`**: Orchestrator — events, holistic handler. Keep minimal.
- **`src/services.py`**: `WorkloadService` + `PebbleService`.
- **`src/configs.py`**: `CharmConfig` — validates charm config.
- **`src/integrations.py`**: Relation wrappers, data transformation, `EnvVarConvertible` implementations.
- **`src/secret.py`**: Juju secrets management.
- **`src/cli.py`**: Wraps `tenant-service` CLI via Pebble exec.
- **`src/constants.py`**: String constants, integration names, ports.
- **`src/env_vars.py`**: `DEFAULT_CONTAINER_ENV`, `EnvVarConvertible` protocol.
- **`src/exceptions.py`**: Custom exception hierarchy.
- **`src/utils.py`**: Condition factories and decorators (`container_connectivity`, `leader_unit`).
- **`src/clients.py`**: HTTP client for OAuth token exchange.

Data flows: **Sources** (Config, Relations, Secrets) → `charm.py` → **Sinks** (Pebble Layer, Relation Databags).
Validate data in `integrations.py` using **Pydantic** models before passing to services.
All data sources implement `EnvVarConvertible` (`to_env_vars() -> EnvVars`).

### Workload CLI

| Command | Usage in charm |
|---------|---------------|
| `tenant-service serve` | Pebble service command |
| `tenant-service version` | Set workload version |
| `tenant-service migrate up --dsn <dsn>` | DB migration (leader only) |
| `tenant-service migrate check --dsn <dsn>` | Check migration status |
| `tenant-service create-fga-model ...` | Create OpenFGA model (leader only) |
| `tenant-service tenant create/list/delete/activate/deactivate/update` | Tenant management (actions) |
| `tenant-service users list/invite/provision/update` | User management (actions) |

## Critical Workflows

- **Formatting**: `tox -e fmt` (isort + ruff format). **Always run before committing.**
- **Linting**: `tox -e lint` (ruff, codespell).
- **Unit Tests**: `tox -e unit` — use `ops.testing` (Scenario), fixtures in `tests/unit/conftest.py`.
- **Integration Tests**: `tox -e integration` — uses `jubilant`.
- **Build**: `charmcraft pack`.
- **Dev Environment**: `tox devenv`.
- **Library Management**: `lib/charms/` files are managed by `charmcraft` — treat as **read-only**.

## Coding Conventions

- **Holistic Handler**: `_holistic_handler` in `charm.py` centralizes reconciliation. Most events delegate to it.
- **Status**: Reported via `_on_collect_status` (`collect-unit-status` hook).
- **Limit `event.defer()`**: Prefer holistic reconciliation over deferring.
- **Type Hinting**: Strict. Use `list`, `dict`, `tuple` (not `typing.List`).
- **Logging**: Lazy formatting (`logger.info("key: %s", value)`), no f-strings.
- **Docstrings**: Google-style for all classes and public methods.
- **Error Handling**: Custom exceptions in `exceptions.py`. Catch in `charm.py` for status.
- **Control Flow**: EAFP over LBYL.
- **No Salesforce**: The tenant-service has no Salesforce integration.

## Relations

### Required
- `pg-database` (`postgresql_client`) — PostgreSQL
- `kratos-info` (`kratos_info`) — Kratos admin endpoint URL

### Optional (existing libraries)
- `openfga` (`openfga`) — Authorization model & tuple storage
- `oauth` (`oauth`) — OAuth2/OIDC provider
- `logging` (`loki_push_api`), `tracing` (`tracing`), `internal-route` (`traefik_route`), `receive-ca-cert` (`certificate_transfer`)

### Provided
- `metrics-endpoint` (`prometheus_scrape`), `grafana-dashboard` (`grafana_dashboard`)
- `hydra-token-hook` (`hydra_token_hook`) — Token enrichment webhook
- `kratos-registration-webhook` (`kratos_registration_webhook`) — Registration webhook
- `kratos-login-webhook` (`kratos_login_webhook`) — Login webhook (new library, see ADR-0004)

### Peer
- `tenant-service` (`tenant_service_peers`) — Share OpenFGA model ID across units

## Actions

- **Auth**: `get-access-token`
- **Tenant management**: `create-tenant`, `list-tenants`, `delete-tenant`, `activate-tenant`, `deactivate-tenant`, `update-tenant`
- **User management**: `list-tenant-users`, `invite-user`, `provision-user`, `update-user-role`

## Testing Strategy

- **Unit**: `ops.testing` (Scenario). Group by events. Mock `Container` and external libs. Mock `KubernetesComputeResourcesPatch` to return `ActiveStatus`.
- **Integration**: `jubilant`. Lifecycle: deploy → scale up → business logic → integrations → actions → scale down → resilience → upgrade → removal. Deploy/removal must be skippable.

## Scoped Guidelines

Detailed guidelines are in scoped instruction files that load automatically:

- **`src/` code**: `.github/instructions/source-code.instructions.md` — EnvVarConvertible protocol, subprocess safety, dataclass hygiene, env var conflicts.
- **`tests/` code**: `.github/instructions/testing.instructions.md` — Test file structure, fixture patterns, mocking rules, action/integration test patterns.
- **Library creation**: `.github/skills/charm-library/SKILL.md` — Creating new charm interface libraries (`lib/charms/`).

## Continuous Improvement

As you work on the codebase, if you identify new patterns or recurring issues not covered here, **update this file** or the scoped instruction/skill files as appropriate.
