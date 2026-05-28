#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing tenant-service info.

This library provides a Python API for both providing and requesting tenant-service
deployment info, such as the HTTP service URL.

## Getting Started

To use the library from the provider side:

In the `charmcraft.yaml` of the charm, add:
```yaml
provides:
  tenant-service-info:
    interface: tenant_service_info
```

Then, to initialise the library:
```python
from charms.tenant_service.v0.tenant_service_info import TenantServiceInfoProvider

class TenantServiceCharm(CharmBase):
    def __init__(self, *args):
        self.tenant_service_info_provider = TenantServiceInfoProvider(self)
        self.framework.observe(
            self.tenant_service_info_provider.on.ready,
            self._on_tenant_service_info_ready,
        )

    def _on_tenant_service_info_ready(self, event):
        self.tenant_service_info_provider.publish_info(service_url="http://svc:8080")
```

To use from the requirer side:

In the `charmcraft.yaml` of the charm, add:
```yaml
requires:
  tenant-service-info:
    interface: tenant_service_info
    optional: true
```

Then, to initialise the library:
```python
from charms.tenant_service.v0.tenant_service_info import TenantServiceInfoRequirer

class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.tenant_service_info = TenantServiceInfoRequirer(self)
        self.framework.observe(
            self.tenant_service_info.on.tenant_service_info_changed,
            self._on_tenant_service_info_changed,
        )
```
"""

import logging
from typing import Optional

from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from pydantic import BaseModel, ValidationError

LIBID = "6257ac767bf04678b4c3f3d2b8edc6e4"
LIBAPI = 0
LIBPATCH = 1

PYDEPS = ["pydantic"]

RELATION_NAME = "tenant-service-info"
INTERFACE_NAME = "tenant_service_info"

logger = logging.getLogger(__name__)


class ProviderData(BaseModel):
    """Data published by the tenant-service into the relation databag."""

    service_url: str
    grpc_url: str


class TenantServiceInfoReadyEvent(EventBase):
    """Event emitted when the provider populates the relation with info."""


class TenantServiceInfoRemovedEvent(EventBase):
    """Event emitted when the relation is removed or data is no longer available."""


class TenantServiceInfoProviderEvents(ObjectEvents):
    """Events for TenantServiceInfoProvider."""

    ready = EventSource(TenantServiceInfoReadyEvent)


class TenantServiceInfoRequirerEvents(ObjectEvents):
    """Events for TenantServiceInfoRequirer."""

    tenant_service_info_changed = EventSource(TenantServiceInfoReadyEvent)
    tenant_service_info_removed = EventSource(TenantServiceInfoRemovedEvent)


class TenantServiceInfoProvider(Object):
    """Provider side of the tenant-service-info relation."""

    on = TenantServiceInfoProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[relation_name].relation_created,
            self._on_relation_created,
        )

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def update_relations_app_data(self, service_url: str, grpc_url: str) -> None:
        """Write service_url and grpc_url into all active relation databags."""
        if not self._charm.unit.is_leader():
            return

        relations = self._charm.model.relations.get(self._relation_name, [])
        for relation in relations:
            relation.data[self._charm.app].update(
                ProviderData(service_url=service_url, grpc_url=grpc_url).model_dump()
            )


class TenantServiceInfoRequirer(Object):
    """Requirer side of the tenant-service-info relation."""

    on = TenantServiceInfoRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        self.framework.observe(
            self._charm.on[relation_name].relation_changed,
            self._on_relation_changed,
        )
        self.framework.observe(
            self._charm.on[relation_name].relation_broken,
            self._on_relation_broken,
        )

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        if not event.relation.app:
            return
        if not event.relation.data.get(event.relation.app):
            return
        self.on.tenant_service_info_changed.emit()

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.on.tenant_service_info_removed.emit()

    def is_ready(self) -> bool:
        """Return True if the relation exists and contains valid data."""
        relation = self._charm.model.get_relation(self._relation_name)
        if not relation or not relation.app:
            return False
        data = relation.data[relation.app]
        return bool(data.get("service_url") and data.get("grpc_url"))

    def get_provider_data(self) -> Optional[ProviderData]:
        """Return parsed ProviderData, or None if unavailable or invalid."""
        relation = self._charm.model.get_relation(self._relation_name)
        if not relation or not relation.app:
            return None
        raw = dict(relation.data[relation.app])
        if not raw.get("service_url") or not raw.get("grpc_url"):
            return None
        try:
            return ProviderData(**raw)
        except ValidationError:
            logger.warning("Invalid data in tenant-service-info relation databag")
            return None

    def get_service_url(self) -> Optional[str]:
        """Return the tenant-service HTTP URL, or None if unavailable."""
        data = self.get_provider_data()
        return data.service_url if data else None

    def get_grpc_url(self) -> Optional[str]:
        """Return the tenant-service gRPC URL, or None if unavailable."""
        data = self.get_provider_data()
        return data.grpc_url if data else None
