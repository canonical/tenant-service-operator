---
name: charm-library
description: "Create new Juju charm interface libraries (lib/charms/). Use when implementing a new relation interface, creating provider/requirer classes, or porting an existing library to support a new webhook type. Covers ProviderData models, secret management, event handling, and publishing."
---

# Charm Library Creation

## When to Use

- Creating a new `lib/charms/<charm>/v0/<library_name>.py` file
- Implementing Provider and Requirer classes for a Juju relation interface
- Porting an existing library for a parallel use case (e.g., registration → login webhook)

## Procedure

### 1. Identify the Reference

Find the closest existing library to use as a template. In the Identity Platform, common references:
- `kratos_registration_webhook.py` — webhook provider with auth secret management
- `hydra_token_hook.py` — simpler webhook provider
- `oauth.py` — complex requirer with client config

### 2. Plan the New Library

Before writing code, determine:

| Field | Value |
|-------|-------|
| Relation name | e.g., `kratos-login-webhook` (kebab-case) |
| Interface name | e.g., `kratos_login_webhook` (snake_case) |
| Provider charm | Which charm provides this data |
| Requirer charm | Which charm consumes this data |
| ProviderData fields | What data crosses the relation boundary |
| Auth mechanism | API key secret, bearer token, or none |

### 3. Create the Library File

Location: `lib/charms/<charm_name>/v0/<library_name>.py`

Required structure:
```python
#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for configuring a <description>."""

# ... imports ...

LIBID = "<placeholder-replace-before-publishing>"
LIBAPI = 0
LIBPATCH = 1

PYDEPS = ["pydantic"]

RELATION_NAME = "<relation-name>"
INTERFACE_NAME = "<interface_name>"
```

### 4. LIBID Generation

- **For development**: Use a placeholder like `"a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"`
- **Before publishing**: Run `charmcraft create-lib charms.<charm>.v0.<lib_name>` in the
  charm that OWNS the library (usually the provider charm) to get a real LIBID
- **Never commit** placeholder LIBIDs to main branches

### 5. Key Components

#### ProviderData Model

Use Pydantic `BaseModel` with serialization support:
```python
class ProviderData(BaseModel):
    url: str
    body: str
    method: str
    # For boolean fields that cross relation databags (stored as strings):
    response_ignore: SerializableBool
    response_parse: SerializableBool
    # Auth fields with defaults:
    auth_type: str = Field(default="api_key")
    auth_config_value: Optional[str] = Field(default=None, exclude=True)
```

Key pattern: `auth_config_value` is `exclude=True` — it's never stored in the relation
databag directly. Instead, a Juju secret is created and `auth_config_value_secret` (the
secret ID) is stored.

#### Secret Management

The Provider creates per-relation Juju secrets using unique labels:
```python
API_KEY_SECRET_LABEL_TEMPLATE = Template("relation-$relation_id-<type>-api-key-secret")
```

Use a **unique** label template to avoid collisions with other libraries
(e.g., `login-api-key-secret` vs `registration-api-key-secret`).

#### Event Flow

| Side | Event | Action |
|------|-------|--------|
| Provider | `relation_created` | Emit `on.ready` |
| Provider | `relation_broken` | Delete secret, emit `on.unavailable` |
| Requirer | `relation_changed` | Validate data, emit `on.ready` |
| Requirer | `relation_broken` | Emit `on.unavailable` |

### 6. Integration Wrapper

After creating the library, create a wrapper class in `src/integrations.py`:
```python
class NewWebhookIntegration:
    def __init__(self, provider: NewWebhookProvider) -> None:
        self._provider = provider

    def is_ready(self) -> bool:
        rel = self._provider._charm.model.get_relation(INTEGRATION_NAME)
        return bool(rel and rel.active)

    def update_relation_data(self, webhook_url: str, api_token: str) -> None:
        self._provider.update_relations_app_data(ProviderData(...))
```

### 7. Wiring Checklist

After creating the library and wrapper:
- [ ] Add relation to `charmcraft.yaml` (provides or requires)
- [ ] Add constant to `src/constants.py`
- [ ] Import and instantiate provider/requirer in `charm.py.__init__`
- [ ] Observe events in `charm.py.__init__`
- [ ] Add `_ensure_*` method to `charm.py`
- [ ] Add to `_holistic_handler` loop
- [ ] Add URL property if webhook
- [ ] Add event handler method
- [ ] Add tests

### 8. Parallel Library Pattern

When creating a parallel library (e.g., login webhook from registration webhook):
1. Copy the reference library
2. Replace ALL name references (class names, relation name, interface name, docstrings)
3. Use a DIFFERENT `API_KEY_SECRET_LABEL_TEMPLATE` to avoid secret collisions
4. Use a new LIBID placeholder
5. Keep the same `ProviderData` model unless the new use case differs

## Constraints

- Libraries in `lib/charms/` are treated as read-only by linters (`ruff`, `mypy`
  exclude pattern in `pyproject.toml`). They won't be auto-formatted.
- Libraries must be self-contained — they cannot import from `src/`.
- PYDEPS list must include all pip dependencies the library needs.
