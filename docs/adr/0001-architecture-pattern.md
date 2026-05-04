# ADR-0001: Follow Hook-Service Charm Architecture Pattern

**Status**: Accepted
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

We need to design the tenant-service charm. The Canonical Identity Team has an established
architecture pattern used by the hook-service-operator and hydra-operator charms. This pattern
uses physical file separation with a holistic handler for reconciliation.

## Decision

We will follow the same architecture and patterns as the hook-service-operator:

- **Physical Separation**: `charm.py` (orchestrator), `services.py` (business logic),
  `configs.py` (config validation), `integrations.py` (relation wrappers), `secret.py`,
  `cli.py`, `utils.py`, `constants.py`, `env_vars.py`, `exceptions.py`.
- **Holistic Handler**: A centralized `_holistic_handler` method that most event handlers
  delegate to. It checks preconditions (`NOOP_CONDITIONS`), runs preparation steps
  (`_ensure_*`), and plans the Pebble layer.
- **Status Management**: Unit status via `collect-unit-status` hook, independent of event
  handling.
- **Data Validation**: Pydantic models at integration boundaries.
- **`EnvVarConvertible` Protocol**: All data sources implement `to_env_vars()` to contribute
  environment variables to the Pebble layer.
- **Testing**: `ops.testing` (Scenario), fixtures in `conftest.py`, mock `Container` and
  external libraries.

## Consequences

- **Positive**: Consistency across Identity Platform charms; team familiarity; easier code
  review; copilot-instructions.md can be shared.
- **Positive**: The hook-service-operator serves as a concrete reference implementation.
- **Negative**: Tight coupling to the established pattern; deviations need justification.

## Alternatives Considered

- **Custom architecture**: Rejected — would diverge from team standards without clear benefit.
