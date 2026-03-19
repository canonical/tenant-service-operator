#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju charm for Identity Platform Tenant Service."""

import logging
import subprocess
from os.path import join
from secrets import token_hex

import ops

logger = logging.getLogger(__name__)


class TenantServiceOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework) -> None:
        super().__init__(framework)


if __name__ == "__main__":  # pragma: nocover
    ops.main(TenantServiceOperatorCharm)
