# ADR-0006: Remove Salesforce Configuration

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

The initial `charmcraft.yaml` was scaffolded from the hook-service-operator and includes
Salesforce-related config options (`salesforce_domain`, `salesforce_consumer_secret`,
`salesforce_enabled`). The tenant-service has no Salesforce integration — Salesforce group
import is a hook-service concern.

## Decision

Remove all Salesforce-related config options from `charmcraft.yaml`. Do not implement
any Salesforce-related logic in the charm.

## Consequences

- **Positive**: Cleaner config; no confusion about unsupported options.
- **Positive**: Fewer secrets to manage.
