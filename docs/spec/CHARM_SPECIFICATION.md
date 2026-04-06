# Tenant Service Operator — Charm Specification

> **Status**: Draft
> **Owner**: Canonical Identity Team
> **Last updated**: 2026-04-03

## 1. Purpose

This document specifies the design of the **tenant-service** Juju charm, which deploys and
manages the [Tenant Service](https://github.com/canonical/tenant-service) on Kubernetes. The
Tenant Service is the multi-tenancy orchestrator for the Canonical Identity Platform, providing
authorization-aware tenant management, user invitation flows, and Hydra/Kratos webhook endpoints
for tenant-aware login and token enrichment.

## 2. Workload Summary

The Tenant Service is a Go application exposing:

| Port | Protocol | Purpose |
|------|----------|---------|
| 8080 | HTTP | REST API via gRPC-Gateway, metrics (`/api/v0/metrics`), status (`/api/v0/status`), webhooks |
| 50051 | gRPC | Native gRPC API for tenant management |

### CLI Commands

| Command | Purpose | Used by charm |
|---------|---------|---------------|
| `tenant-service serve` | Start the HTTP + gRPC server | Yes — Pebble service command |
| `tenant-service migrate up --dsn <dsn>` | Run DB migrations | Yes — leader unit on DB ready |
| `tenant-service migrate check --dsn <dsn>` | Check migration status | Yes — readiness gate |
| `tenant-service create-fga-model` | Create OpenFGA authorization model | Yes — leader unit on OpenFGA ready |
| `tenant-service version` | Print version | Yes — set workload version |
| `tenant-service token` | Generate JWT access token | Yes — `get-access-token` action |

### Environment Variables

The charm maps integrations and config to the following workload environment variables.
See `internal/config/specs.go` in the tenant-service repo for the full list.

**From database integration:**
- `DSN` — PostgreSQL connection string

**From OpenFGA integration:**
- `AUTHORIZATION_ENABLED`, `OPENFGA_API_SCHEME`, `OPENFGA_API_HOST`, `OPENFGA_API_TOKEN`,
  `OPENFGA_STORE_ID`, `OPENFGA_AUTHORIZATION_MODEL_ID`

**From tracing integration:**
- `TRACING_ENABLED`, `OTEL_HTTP_ENDPOINT`, `OTEL_GRPC_ENDPOINT`

**From OAuth integration or charm config:**
- `AUTHENTICATION_ENABLED`, `AUTHENTICATION_ISSUER`, `AUTHENTICATION_JWKS_URL`,
  `AUTHENTICATION_ALLOWED_SUBJECTS`, `AUTHENTICATION_REQUIRED_SCOPE`

**From Kratos integration:**
- `KRATOS_ADMIN_URL`

**From charm config:**
- `LOG_LEVEL`, `PORT`, `GRPC_PORT`, `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`,
  `INVITATION_LIFETIME`

**From secrets:**
- `WEBHOOKS_API_TOKEN` — API token used to authenticate Kratos/Hydra webhook calls

## 3. Architecture

Follows the standard Identity Platform charm pattern (Physical Separation & Data Flow):

```
src/
├── charm.py          # Orchestrator — event handling, holistic handler
├── services.py       # WorkloadService + PebbleService
├── configs.py        # CharmConfig — validates charm config options
├── integrations.py   # Relation wrappers: DatabaseConfig, TracingData,
│                     # OpenFGAIntegration, KratosInfoIntegration,
│                     # KratosRegistrationWebhookIntegration,
│                     # HydraTokenHookIntegration, OAuthIntegration,
│                     # InternalIngressData, TLSCertificates, PeerData
├── constants.py      # All string constants, integration names, ports
├── env_vars.py       # DEFAULT_CONTAINER_ENV, EnvVarConvertible protocol
├── secret.py         # Secrets class — manages Juju secrets
├── cli.py            # CommandLine — wraps `tenant-service` CLI via Pebble exec
├── exceptions.py     # CharmError hierarchy
├── utils.py          # NOOP_CONDITIONS, condition factories, decorators
├── clients.py        # HTTPClient for OAuth token exchange (action support)
├── grafana_dashboards/
├── loki_alert_rules/
├── prometheus_alert_rules/
└── templates/
    └── internal-route.json.j2
```

### Data Flow

```
Sources                          Orchestration              Sinks
─────────────────────           ──────────────             ─────────────────
CharmConfig (configs.py)    ──→                        ──→ Pebble Layer (env vars)
DatabaseConfig              ──→                        ──→
TracingData                 ──→  charm.py               ──→
OpenFGAIntegration          ──→  _holistic_handler()   ──→
KratosInfoIntegration       ──→                        ──→
OAuthIntegration            ──→                        ──→
Secrets                     ──→                        ──→ Relation Databags
                                                           (hydra-token-hook,
                                                            kratos-registration-webhook)
```

## 4. Relations

### 4.1 Required Relations

| Relation Name | Interface | Direction | Library | Purpose |
|---------------|-----------|-----------|---------|---------|
| `pg-database` | `postgresql_client` | requires | `charms.data_platform_libs.v0.data_interfaces` | PostgreSQL database for tenant/membership storage |
| `kratos-info` | `kratos_info` | requires | `charms.kratos.v0.kratos_info` | Fetch Kratos admin endpoint URL (`KRATOS_ADMIN_URL`) |

### 4.2 Optional Relations (existing libraries)

| Relation Name | Interface | Direction | Library | Purpose |
|---------------|-----------|-----------|---------|---------|
| `openfga` | `openfga` | requires | `charms.openfga_k8s.v1.openfga` | Authorization model & tuple storage |
| `oauth` | `oauth` | requires | `charms.hydra.v0.oauth` | Receive OAuth2/OIDC provider info and client credentials |
| `logging` | `loki_push_api` | requires | `charms.loki_k8s.v1.loki_push_api` | Forward logs to Loki |
| `tracing` | `tracing` | requires | `charms.tempo_coordinator_k8s.v0.tracing` | Send traces to Tempo |
| `internal-route` | `traefik_route` | requires | `charms.traefik_k8s.v0.traefik_route` | Cross-cluster internal ingress |
| `receive-ca-cert` | `certificate_transfer` | requires | `charms.certificate_transfer_interface.v1.certificate_transfer` | Receive CA certificates for TLS |
| `metrics-endpoint` | `prometheus_scrape` | provides | `charms.prometheus_k8s.v0.prometheus_scrape` | Expose Prometheus metrics |
| `grafana-dashboard` | `grafana_dashboard` | provides | `charms.grafana_k8s.v0.grafana_dashboard` | Dashboard JSON |

### 4.3 Relations Requiring New/Extended Libraries

| Relation Name | Interface | Direction | Library Source | Purpose | Decision |
|---------------|-----------|-----------|---------------|---------|----------|
| `hydra-token-hook` | `hydra_token_hook` | provides | `charms.hydra.v0.hydra_token_hook` (existing) | Register webhook URL with Hydra for token enrichment (`/api/v0/webhooks/token`) | **Reuse existing library** — same `ProviderData` model; see [ADR-0002](../adr/0002-hydra-token-hook-reuse.md) |
| `kratos-registration-webhook` | `kratos_registration_webhook` | provides | `charms.kratos.v0.kratos_registration_webhook` (existing) | Register registration webhook with Kratos (`/api/v0/webhooks/registration`) | **Reuse existing library** — see [ADR-0003](../adr/0003-kratos-registration-webhook.md) |
| `kratos-login-webhook` | `kratos_login_webhook` | provides | **New library** (`charms.kratos.v0.kratos_login_webhook`) | Register login validation webhook with Kratos (`/api/v0/webhooks/login`) | **New library** (Option B) — see [ADR-0004](../adr/0004-kratos-login-webhook.md) |

### 4.4 Peer Relation

| Relation Name | Interface | Purpose |
|---------------|-----------|---------|
| `tenant-service` | `tenant_service_peers` | Share OpenFGA model ID across units |

### 4.5 Relation Summary Diagram

```
                    ┌───────────────────────┐
                    │   tenant-service      │
                    │   (this charm)        │
                    └───────┬───────────────┘
        requires            │            provides
        ────────            │            ────────
  pg-database ◄─────────────┤──────────► metrics-endpoint
  openfga ◄─────────────────┤──────────► grafana-dashboard
  kratos-info ◄─────────────┤──────────► hydra-token-hook
  oauth ◄───────────────────┤──────────► kratos-registration-webhook
  logging ◄─────────────────┤──────────► kratos-login-webhook (NEW)
  tracing ◄─────────────────┤
  internal-route ◄──────────┤
  receive-ca-cert ◄─────────┤
                            │
                    peers: tenant-service
```

## 5. Configuration

### 5.1 Config Options

| Option | Type | Default | Purpose |
|--------|------|---------|---------|
| `http_proxy` | string | `""` | HTTP proxy URL |
| `https_proxy` | string | `""` | HTTPS proxy URL |
| `no_proxy` | string | `""` | Proxy exclusion list |
| `log_level` | string | `"info"` | Log level (`info`, `debug`, `warning`, `error`, `critical`) |
| `cpu` | string | unset | K8s CPU resource limit |
| `memory` | string | unset | K8s memory resource limit |
| `authorization_enabled` | boolean | `true` | Enable OpenFGA authorization checks |
| `authn_allowed_subjects` | string | `""` | Comma-separated allowed JWT subject IDs |
| `authn_allowed_scope` | string | `""` | Required OAuth2 scope |
| `authn_issuer` | string | `""` | JWT issuer URL (mutually exclusive with `oauth` relation) |
| `authn_jwks_url` | string | `""` | JWKS endpoint (mutually exclusive with `oauth` relation) |
| `invitation_lifetime` | string | `"24h"` | Duration an invitation/recovery link remains valid |

## 6. Actions

The charm exposes Juju actions to simplify common tenant and user management workflows.
All management actions require the workload to be running and the database to be available.
Actions that modify data run on the leader unit via the `tenant-service` CLI.

### 6.1 Authentication

| Action | Description | Requirements |
|--------|-------------|--------------|
| `get-access-token` | Generate a JWT token using the OAuth client credentials flow | `oauth` integration |

### 6.2 Tenant Management

| Action | Description | Parameters |
|--------|-------------|------------|
| `create-tenant` | Create a new tenant | `name` (required) |
| `list-tenants` | List all tenants | — |
| `delete-tenant` | Delete a tenant | `tenant-id` (required) |
| `activate-tenant` | Enable a disabled tenant | `tenant-id` (required) |
| `deactivate-tenant` | Disable an active tenant | `tenant-id` (required) |
| `update-tenant` | Update a tenant's name | `tenant-id` (required), `name` (required) |

### 6.3 User Management

| Action | Description | Parameters |
|--------|-------------|------------|
| `list-tenant-users` | List all users in a tenant | `tenant-id` (required) |
| `invite-user` | Send an invitation email to join a tenant | `tenant-id` (required), `email` (required), `role` (required) |
| `provision-user` | Directly add a user to a tenant (no invitation) | `tenant-id` (required), `email` (required), `role` (required) |
| `update-user-role` | Update a user's role within a tenant | `tenant-id` (required), `user-id` (required), `role` (required) |

## 7. Secrets

| Label | Keys | Purpose |
|-------|------|---------|
| `apitokensecret` | `api-token` | Shared API token for authenticating webhook calls from Kratos/Hydra. Generated by leader, stored as Juju secret, passed to Hydra/Kratos via relation data and to the workload as `WEBHOOKS_API_TOKEN`. |

## 8. Holistic Handler

The charm uses the centralized `_holistic_handler` pattern. Most event handlers delegate to it.

### Preconditions (NOOP_CONDITIONS)

If any of these return `False`, the handler returns early without action:

1. `container_connectivity` — Pebble container is reachable
2. `database_integration_exists` — `pg-database` relation exists
3. `database_resource_is_created` — Database has been provisioned
4. `authentication_config_is_valid` — No conflicting OAuth config

### Preparation Steps

Executed in order; each returns `bool`. Short-circuit on failure:

1. `_ensure_secrets` — Create API token secret if leader
2. `_ensure_hydra_relation` — Push webhook URL + token to Hydra via `hydra-token-hook` relation
3. `_ensure_kratos_registration_webhook` — Push webhook URL + token to Kratos via `kratos-registration-webhook` relation
4. `_ensure_kratos_login_webhook` — Push webhook URL + token to Kratos via `kratos-login-webhook` relation (NEW)
5. `_ensure_internal_ingress` — Submit Traefik route config
6. `_ensure_database_migration` — Run `tenant-service migrate up` (leader only)
7. `_ensure_openfga_model` — Run `tenant-service create-fga-model` (leader only)
8. `_ensure_tls` — Sync CA certificates to workload container

### Final Step

If all preparation steps succeed → `self._pebble_service.plan(self._pebble_layer)`

## 9. Status Management

Status is reported via `_on_collect_status` (Juju `collect-unit-status` hook):

| Condition | Status |
|-----------|--------|
| Container not connected | `WaitingStatus("Container is not connected yet")` |
| Secrets not ready | `WaitingStatus("Waiting for secrets creation")` |
| Workload failing (check failures > 0) | `BlockedStatus("Failed to start the service...")` |
| Missing `pg-database` | `BlockedStatus("Missing integration pg-database")` |
| Database not created | `WaitingStatus("Waiting for database creation")` |
| Missing `openfga` (if authorization_enabled) | `BlockedStatus("Missing integration openfga")` |
| OpenFGA store not ready | `WaitingStatus("Waiting for openfga store...")` |
| Missing `kratos-info` | `BlockedStatus("Missing integration kratos-info")` |
| Migration pending (leader) | `WaitingStatus("Waiting for database migration")` |
| Migration pending (non-leader) | `WaitingStatus("Waiting for leader unit to run the migration")` |
| Migration check failed | `BlockedStatus("Migration check failed: ...")` |
| Invalid authentication config | `BlockedStatus("Invalid authentication configuration")` |
| Resource patch failed | from `KubernetesComputeResourcesPatch.get_status()` |
| All good | `ActiveStatus()` |

## 10. Pebble Layer

```python
PEBBLE_LAYER_DICT: LayerDict = {
    "summary": "tenant-service-operator layer",
    "description": "pebble config layer for tenant-service-operator",
    "services": {
        "tenant-service": {
            "override": "replace",
            "summary": "entrypoint of the tenant-service image",
            "command": "tenant-service serve",
            "startup": "disabled",
        }
    },
    "checks": {
        "ready": {
            "override": "replace",
            "http": {"url": "http://localhost:8080/api/v0/status"},
        },
    },
}
```

Environment variables are composed from multiple `EnvVarConvertible` sources:
- `TracingData`
- `DatabaseConfig`
- `Secrets`
- `CharmConfig`
- `OpenFGAModelData`
- `OpenFGAIntegrationData`
- `OAuthProviderData`
- `KratosInfoData` (new — provides `KRATOS_ADMIN_URL`)

## 11. gRPC Exposure

The tenant-service exposes both HTTP (:8080) and gRPC (:50051) ports. Both should be opened by
the charm. The HTTP port is used for the REST API, webhooks, metrics, and status. The gRPC port
is used by native gRPC clients.

**Open question**: Traefik gRPC ingress support needs investigation. The `internal-route`
relation uses `traefik_route` which works with HTTP. gRPC may require a separate route config
or H2C passthrough. See [ADR-0005](../adr/0005-grpc-exposure.md).

For the initial release, both ports are opened via `unit.open_port()`, but only HTTP is routed
through Traefik ingress. gRPC access is available via direct pod/service IP.

## 12. Deployment Topology

```
juju deploy tenant-service --trust
juju deploy postgresql-k8s --channel 14/stable --trust
juju deploy openfga-k8s --channel latest/edge --trust
juju deploy kratos --channel latest/edge --trust
juju deploy hydra --channel latest/edge --trust
juju deploy traefik-k8s --channel latest/stable --trust
juju deploy self-signed-certificates --channel latest/stable --trust

# Required
juju integrate tenant-service:pg-database postgresql-k8s
juju integrate tenant-service:openfga openfga-k8s

# Kratos (admin URL + webhooks)
juju integrate tenant-service:kratos-info kratos:kratos-info
juju integrate tenant-service:kratos-registration-webhook kratos:kratos-registration-webhook
# juju integrate tenant-service:kratos-login-webhook kratos:kratos-login-webhook  # NEW

# Hydra (token hook + OAuth)
juju integrate tenant-service:hydra-token-hook hydra
juju integrate tenant-service:oauth hydra

# Observability
juju integrate tenant-service:logging loki
juju integrate tenant-service:tracing tempo
juju integrate tenant-service:metrics-endpoint prometheus

# Ingress
juju integrate tenant-service:internal-route traefik-k8s

# TLS
juju integrate traefik-k8s:certificates self-signed-certificates
juju integrate tenant-service:receive-ca-cert self-signed-certificates
```

## 13. Implementation Phases

### Phase 1 — Core Charm (MVP)

- [ ] `src/charm.py` — Orchestrator with holistic handler
- [ ] `src/services.py` — WorkloadService + PebbleService
- [ ] `src/configs.py` — CharmConfig with validation
- [ ] `src/integrations.py` — DatabaseConfig, TracingData, OpenFGAIntegration, PeerData,
      TLSCertificates, InternalIngressData, OAuthIntegration
- [ ] `src/constants.py`, `src/env_vars.py`, `src/exceptions.py`, `src/secret.py`
- [ ] `src/cli.py` — CommandLine wrapper (version, migrate, create-fga-model)
- [ ] `src/utils.py` — Conditions and helpers
- [ ] `templates/internal-route.json.j2`
- [ ] Unit tests (`tests/unit/`)
- [ ] `charmcraft.yaml` updates (remove Salesforce config)

### Phase 2 — Kratos Integration

- [ ] `kratos-info` relation — fetch `KRATOS_ADMIN_URL` from Kratos
- [ ] `kratos-registration-webhook` relation — register registration webhook
- [ ] Investigate and implement `kratos-login-webhook` (new library decision)

### Phase 3 — Hydra Integration

- [ ] `hydra-token-hook` relation — register token hook webhook
- [ ] `oauth` relation — receive OAuth client credentials
- [ ] `get-access-token` action

### Phase 4 — Observability & Polish

- [ ] Grafana dashboards
- [ ] Loki alert rules
- [ ] Prometheus alert rules
- [ ] Integration tests (`tests/integration/`)

## 14. Open Questions

| # | Question | Status | ADR |
|---|----------|--------|-----|
| 1 | Can we reuse `kratos_registration_webhook` library as-is for the registration hook? | To verify | [ADR-0003](../adr/0003-kratos-registration-webhook.md) |
| 2 | How to expose gRPC through Traefik? | To investigate | [ADR-0005](../adr/0005-grpc-exposure.md) |

## 15. Known Limitations

### ⚠️ Hydra Token Hook Coexistence (CRITICAL)

Hydra supports only **one** `hydra-token-hook` relation at a time. The tenant-service
replaces the hook-service as the token hook provider. This means hook-service group
enrichment is lost when tenant-service takes over. **This must be resolved at the
application level before production use where both services coexist.**

See [ADR-0002](../adr/0002-hydra-token-hook-reuse.md) for details and possible resolutions.
