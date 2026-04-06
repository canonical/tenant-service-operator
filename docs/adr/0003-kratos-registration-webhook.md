# ADR-0003: Reuse kratos_registration_webhook Library

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

The tenant-service exposes a registration webhook at `POST /api/v0/webhooks/registration`.
Kratos calls this after a new identity is persisted, and the tenant-service creates a shadow
tenant and assigns the user as owner.

The `charms.kratos.v0.kratos_registration_webhook` library already exists and is consumed by
the kratos-operator (via `requires: kratos-registration-webhook`). The `ProviderData` model
includes:
- `url` — webhook URL
- `body` — request body template
- `method` — HTTP method
- `response_ignore` / `response_parse` — response handling flags
- `auth_type`, `auth_config_name`, `auth_config_value`, `auth_config_in` — authentication

The hook-service-operator does **not** currently use this library (it uses the
`hydra-token-hook` relation instead). Looking at the kratos-operator's `charmcraft.yaml`, it
has `requires: kratos-registration-webhook` with the `kratos_registration_webhook` interface.

## Decision

Reuse `charms.kratos.v0.kratos_registration_webhook` for the registration webhook.

The tenant-service charm will:
1. Use `KratosRegistrationWebhookProvider` to register the webhook.
2. Set `url` to `{base_url}/api/v0/webhooks/registration`.
3. Set `body` to the appropriate Kratos jsonnet/template format that extracts `user_id` and
   `email` from the Kratos identity.
4. Set `auth_config_value` to the `WEBHOOKS_API_TOKEN` secret.

**Note**: The exact `body` template needs to match what the tenant-service expects. The
`KratosIdentity` type in `pkg/webhooks/types.go` expects `{"user_id": "...", "email": "..."}`.
The body template must use Kratos's flow context to extract these fields.

## Consequences

- **Positive**: Reuses existing, tested library. Kratos already supports this integration.
- **Positive**: The relation can coexist with other registration webhook providers since
  Kratos supports multiple webhook integrations.
- **Negative**: The `body` template format is tightly coupled to the tenant-service's
  expected payload format — changes in either side need coordination.

## Alternatives Considered

- **New library**: Rejected — the existing library is general enough for registration webhooks.
