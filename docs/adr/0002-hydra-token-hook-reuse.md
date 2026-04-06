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

## Decision

Reuse `charms.hydra.v0.hydra_token_hook` as-is for the `hydra-token-hook` relation.

The tenant-service charm will:
1. Use `HydraHookProvider` to register the webhook URL `/api/v0/webhooks/token`.
2. Pass the `WEBHOOKS_API_TOKEN` secret as the `auth_config_value`.
3. Use the internal ingress URL (or in-cluster service URL) as the base.

**Important**: Hydra currently supports only **one** token hook integration. If both
hook-service and tenant-service need to be registered simultaneously, this is a problem
that requires upstream changes to Hydra. For now, the tenant-service would **replace** the
hook-service as the token hook provider.

## Consequences

- **Positive**: No new library to write or maintain. Battle-tested code.
- **Negative**: Only one charm can provide the `hydra-token-hook` at a time. If both
  hook-service and tenant-service need to coexist, the hook-service's group enrichment
  may need to be absorbed into tenant-service or a composition pattern is needed.

## ⚠️ TODO: TOKEN HOOK COEXISTENCE (CRITICAL)

**Hydra supports only one `hydra-token-hook` relation at a time.** Currently, the
tenant-service replaces the hook-service as the token hook provider. This means:

1. **hook-service group enrichment is lost** when tenant-service takes over.
2. If both charms are deployed, only one can be integrated with Hydra's `hydra-token-hook`.
3. **This must be resolved at the application level** before production use where both
   services coexist.

Possible resolutions:
- Absorb hook-service's group enrichment logic into tenant-service.
- Implement a webhook chaining/composition pattern in Hydra.
- Create a proxy service that chains both webhooks.

**This is a known limitation for the initial release. Track and resolve before GA.**

## Alternatives Considered

- **New interface**: Rejected — the protocol is identical; creating a new interface
  just changes the name.
- **Extend the library for multiple hooks**: Out of scope for this charm; would be
  a Hydra-operator change.
