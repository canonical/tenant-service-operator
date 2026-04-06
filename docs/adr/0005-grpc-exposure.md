# ADR-0005: gRPC Port Exposure Strategy

**Status**: Proposed
**Date**: 2026-04-03
**Deciders**: Canonical Identity Team

## Context

The tenant-service exposes two ports:
- **8080** (HTTP) — REST API via gRPC-Gateway, webhooks, metrics, health
- **50051** (gRPC) — Native gRPC API

Both ports should be accessible. The HTTP port is used by webhooks (Kratos, Hydra),
Prometheus scraping, and human/browser clients. The gRPC port is used by native gRPC clients.

The charm uses the `traefik_route` library for ingress via `internal-route`. Traefik supports
gRPC proxying (it can handle H2C/gRPC connections), but the charmed Traefik integration
`traefik_route` has not been tested extensively with gRPC.

## Decision

**Phase 1 (initial release):**
- Open both ports via `unit.open_port()` (TCP 8080 and TCP 50051).
- Configure `internal-route` for HTTP only (port 8080), following the same pattern as
  hook-service-operator.
- gRPC is accessible via direct service/pod IP within the cluster.

**Phase 2 (future):**
- Investigate Traefik gRPC routing support in the charmed ecosystem.
- If supported, add a gRPC route configuration to the `internal-route.json.j2` template.
- Alternatively, consider a separate `grpc-route` relation if needed.

## Consequences

- **Positive**: HTTP ingress works identically to hook-service (proven pattern).
- **Positive**: gRPC is still accessible for in-cluster consumers.
- **Negative**: External gRPC access requires manual network configuration until Phase 2.

## Alternatives Considered

- **Expose only HTTP**: Rejected — the gRPC API is a first-class interface.
- **Add gRPC route to internal-route immediately**: Risky without testing; deferred.
