output "smf_application_name" {
  description = "Name of the deployed application."
  value       = juju_application.smf.name
}