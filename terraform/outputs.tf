# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.application.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    logging         = "logging"
    tracing         = "tracing"
    openfga         = "openfga"
    oauth           = "oauth"
    receive-ca-cert = "receive-ca-cert"
    pg-database     = "pg-database"
    internal-route  = "internal-route"
  }
}
