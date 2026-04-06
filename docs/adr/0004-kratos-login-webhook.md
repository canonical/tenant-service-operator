# ADR-0004: Kratos Login Webhook — New Library

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

The tenant-service exposes a login validation webhook at `POST /api/v0/webhooks/login`. Kratos
calls this during the login flow to:
1. Verify the user's tenant membership.
2. Perform lazy reconciliation for orphaned identities (users who registered but whose
   registration webhook failed).

Looking at the existing Kratos charm libraries:
- `kratos_registration_webhook` — handles **registration** webhooks. The `ProviderData` model
  works for registration but the library is specifically named and documented for registration.
- `kratos_info` — provides endpoint information, not webhook configuration.

The kratos-operator's `charmcraft.yaml` does **not** currently have a relation for login
webhooks — only `kratos-registration-webhook`.

## Decision

**Create a new `kratos_login_webhook` library** (Option B).

Create a parallel library (`charms.kratos.v0.kratos_login_webhook`) with the same `ProviderData`
model but a different relation name and interface.

This is the fastest path to a working charm:
- No breaking changes to existing consumers.
- Can be developed independently from kratos-operator.
- Code duplication is minimal (the `ProviderData` model can be shared or copied).
- The kratos-operator would add a new `requires: kratos-login-webhook` relation.

A generic `kratos_webhook` v1 library could be pursued later as a consolidation effort.

## Consequences

- **Positive**: Unblocks tenant-service charm development.
- **Negative**: Requires a PR to kratos-operator to add the new relation.
- **Negative**: Two very similar libraries until a v1 consolidation happens.

## Action Items

- [ ] Confirm with kratos-operator maintainers that adding `kratos-login-webhook` relation
      is acceptable.
- [ ] Determine the exact Kratos `body` template for the login webhook payload
      (`KratosLoginPayload`: `identity_id`, `email`, `tenant_id`).
- [ ] Create the library in this repo (or in kratos-operator) and publish via `charmcraft`.
