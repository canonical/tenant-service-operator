# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Exceptions."""


class CharmError(Exception):
    """Base class for custom charm errors."""


class PebbleError(CharmError):
    """Error for pebble related operations."""


class MigrationError(CharmError):
    """Error for database migration."""


class MigrationCheckError(CharmError):
    """Error for database migration check."""


class CreateFgaModelError(CharmError):
    """Error when creating an OpenFGA authorization model."""
