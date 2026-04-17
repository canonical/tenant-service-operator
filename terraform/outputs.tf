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
    kratos-info     = "kratos-info"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    tenant-service-info         = "tenant-service-info"
    hydra-token-hook            = "hydra-token-hook"
    kratos-registration-webhook = "kratos-registration-webhook"
    kratos-login-webhook        = "kratos-login-webhook"
  }
}
