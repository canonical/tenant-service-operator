/**
 * # Terraform Module for Tenant Service K8s Operator
 *
 * This is a Terraform module facilitating the deployment of the
 * tenant-service charm using the Juju Terraform provider.
 */

locals {
  charmcraft = yamldecode(file("${path.module}/../charmcraft.yaml"))
  oci_image = {
    "oci-image" : local.charmcraft.resources.oci-image.upstream-source
  }
  resources = merge(local.oci_image, var.resources)
}

resource "juju_application" "application" {
  name       = var.app_name
  model_uuid = var.model
  trust      = true
  config = merge(
    var.config,
    { salesforce_consumer_secret = format("secret:%s", var.salesforce_credentials_secret_id) }
  )
  constraints = var.constraints
  resources   = local.resources
  units       = var.units

  charm {
    name     = "tenant-service"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
