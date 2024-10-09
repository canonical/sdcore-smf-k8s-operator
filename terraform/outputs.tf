# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.smf.name
}

output "requires" {
  value = {
    certificates  = "certificates"
    fiveg_nrf     = "fiveg_nrf"
    logging       = "logging"
    sdcore_config = "sdcore_config"
  }
}

output "provides" {
  value = {
    metrics = "metrics-endpoint"
  }
}
