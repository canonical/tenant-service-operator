# ADR-0002: Reuse hydra_token_hook Library for Token Hook

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

The tenant-service exposes a token enrichment webhook at `POST /api/v0/webhooks/token`. This
webhook is called by Hydra during OAuth2 token issuance to inject `tenant_id` claims.

The hook-service-operator already uses the `charms.hydra.v0.hydra_token_hook` library to provide
this exact type of integration to Hydra. Hydra's `charmcraft.yaml` has a `requires:
hydra-token-hook` with interface `hydra_token_hook`.

The `HydraHookProvider` class sends a `ProviderData` object containing:
- `url` — the webhook URL
- `auth_config_value` — the API token
- `auth_config_name` — header name ("Authorization")
- `auth_config_in` — where the auth goes ("header")

This matches exactly what the tenant-service needs.

However, Hydra supports only **one** `hydra-token-hook` relation at a time. Both
tenant-service and hook-service need to enrich OAuth tokens — tenant-service with `tenant_id`
and hook-service with user `groups`. This conflict was resolved at the application level:
hook-service now calls tenant-service's `LookupTenantsByIdentityID` gRPC API to resolve tenant
membership, injecting both `tenant_id` and `groups` into the token in a single hook invocation.
Hook-service discovers the tenant-service URL via the `tenant-service-info` Juju relation.

## Decision

Reuse `charms.hydra.v0.hydra_token_hook` as-is for the `hydra-token-hook` relation. Both
deployment topologies are supported:

### Topology A — With hook-service (recommended for new deployments)

Hook-service is the single Hydra token hook provider. It handles both `groups` and `tenant_id`
enrichment by calling tenant-service internally.

```
hydra ←── hydra-token-hook ──→ hook-service
hook-service ←── tenant-service-info ──→ tenant-service
```

In this topology, do **not** integrate `tenant-service:hydra-token-hook` with Hydra.

### Topology B — Without hook-service (standalone tenant-service)

Tenant-service provides the token hook directly to Hydra. Only `tenant_id` is injected;
`groups` enrichment is not available.

```
hydra ←── hydra-token-hook ──→ tenant-service
```

### Constraint

Only one charm may be integrated with `hydra:hydra-token-hook` at a time. If both hook-service
and tenant-service are integrated with Hydra simultaneously, whichever was integrated last will
be active — the other will be silently overwritten by Hydra.

## Consequences

- **Positive**: No new library to write or maintain. Battle-tested code.
- **Positive**: Supports both deployment topologies without code changes.
- **Positive**: Existing deployments using tenant-service directly continue to work.
- **Negative**: Operators must be aware they cannot integrate both charms with Hydra
  simultaneously. This is documented in the charm README and specification.

## Alternatives Considered

- **New interface**: Rejected — the protocol is identical; creating a new interface
  just changes the name.
- **Extend the library for multiple hooks**: Out of scope for this charm; would be
  a Hydra-operator change.
