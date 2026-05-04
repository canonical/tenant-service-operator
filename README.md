# Charmed Tenant Service for the Canonical Identity Platform

[![CharmHub Badge](https://charmhub.io/tenant-service/badge.svg)](https://charmhub.io/tenant-service)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/tenant-service-operator?label=License)](https://github.com/canonical/tenant-service-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/tenant-service-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/tenant-service-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

Python Operator for the Canonical Identity Platform Tenant Service

## Hydra Token Hook

This charm provides a `hydra-token-hook` relation that registers a token enrichment
webhook with Hydra to inject `tenant_id` claims into OAuth2 access and ID tokens.

**Important:** Hydra supports only **one** `hydra-token-hook` integration at a time.
Two deployment topologies are available:

| Topology | Hook provider | Token claims | When to use |
|----------|--------------|--------------|-------------|
| **With hook-service** (recommended) | hook-service | `groups` + `tenant_id` | Full Identity Platform deployments |
| **Without hook-service** | tenant-service | `tenant_id` only | Standalone tenant-service deployments |

When **hook-service** is deployed, it should be the sole `hydra-token-hook` provider.
Hook-service discovers tenant-service via the `tenant-service-info` relation and calls
its lookup API internally, so both `groups` and `tenant_id` are enriched in a single
hook invocation. Do **not** also integrate `tenant-service:hydra-token-hook` with Hydra
in this topology.

When **hook-service** is not deployed, tenant-service can provide the hook directly:

```bash
juju integrate tenant-service:hydra-token-hook hydra
```

See [ADR-0007](docs/adr/0007-remove-hydra-token-hook.md) for the full rationale.

## Security

Please see [SECURITY.md](https://github.com/canonical/tenant-service-operator/blob/main/SECURITY.md)
for guidelines on reporting security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/tenant-service-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The Charmed Tenant Service is free software, distributed under the Apache
Software License, version 2.0.
See [LICENSE](https://github.com/canonical/tenant-service-operator/blob/main/LICENSE)
for more information.
