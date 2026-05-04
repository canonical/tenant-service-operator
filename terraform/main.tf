/**
 * # Terraform Module for Tenant Service K8s Operator
 *
 * This is a Terraform module facilitating the deployment of the
 * tenant-service charm using the Juju Terraform provider.
 */

resource "juju_application" "application" {
  name       = var.app_name
  model_uuid = var.model
  trust      = true
  config = merge(
    var.config,
  )
  constraints = var.constraints
  resources   = var.resources
  units       = var.units

  charm {
    name     = "tenant-service"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
