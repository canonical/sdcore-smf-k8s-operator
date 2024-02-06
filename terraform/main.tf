resource "juju_application" "smf" {
  name  = "smf"
  model = var.model_name

  charm {
    name    = "sdcore-smf-k8s"
    channel = var.channel
  }

  units = 1
  trust = true
}

resource "juju_integration" "smf-db" {
  model = var.model_name

  application {
    name     = juju_application.smf.name
    endpoint = "database"
  }

  application {
    name     = var.db_application_name
    endpoint = "database"
  }
}

resource "juju_integration" "smf-certs" {
  model = var.model_name

  application {
    name     = juju_application.smf.name
    endpoint = "certificates"
  }

  application {
    name     = var.certs_application_name
    endpoint = "certificates"
  }
}

resource "juju_integration" "smf-nrf" {
  model = var.model_name

  application {
    name     = juju_application.smf.name
    endpoint = "fiveg_nrf"
  }

  application {
    name     = var.nrf_application_name
    endpoint = "fiveg-nrf"
  }
}

