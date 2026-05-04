---
description: "Use when writing or modifying charm source code modules. Covers common pitfalls, EnvVarConvertible protocol, subprocess safety, and dataclass hygiene."
applyTo: "src/**"
---

# Source Code Guidelines

## EnvVarConvertible Protocol

All classes that contribute environment variables to the Pebble layer must implement:

```python
def to_env_vars(self) -> EnvVars:  # from env_vars.py, NOT ServiceConfigs
```

- Return type MUST be `EnvVars` (from `env_vars.py`), not `ServiceConfigs` or `dict[str, Any]`.
- Only include keys the workload binary actually reads as environment variables.
- Do NOT spread raw charm config keys (e.g., `authn_issuer`) — the workload expects
  properly named vars like `AUTHENTICATION_ISSUER`.
- Values flow directly into the Pebble layer environment via `render_pebble_layer()`.

## Subprocess Safety

Always use `check=True` with `subprocess.run`. Wrap in try/except if failure should not block:

```python
try:
    subprocess.run(["update-ca-certificates", ...], check=True)
except subprocess.CalledProcessError:
    logger.exception("Failed to update CA certificates")
```

## Dataclass Hygiene

- Python silently allows duplicate field definitions in dataclasses — the second shadows
  the first with no error. Always verify field uniqueness.
- Use `frozen=True` for data source classes to prevent accidental mutation.

## Integration Wrapper Pattern

Each relation wrapper in `integrations.py` follows this structure:

```python
class SomeIntegration:
    def __init__(self, provider_or_requirer: LibraryClass) -> None:
        self._provider = provider_or_requirer

    def is_ready(self) -> bool:
        rel = self._provider._charm.model.get_relation(INTEGRATION_NAME)
        return bool(rel and rel.active)

    def update_relation_data(self, ...) -> None:
        self._provider.update_relations_app_data(ProviderData(...))
```

## Env Var Conflict Prevention

When multiple sources set the same env var (e.g., `AUTHORIZATION_ENABLED`), the LAST
source in the `render_pebble_layer()` call wins (dict.update order). Document which source
is authoritative and ensure only one source sets each key.
