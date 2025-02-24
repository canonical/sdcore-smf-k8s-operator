# Aether SD-Core SMF Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-smf-k8s/badge.svg)](https://charmhub.io/sdcore-smf-k8s)

Charmed Operator for the Aether SD-Core Session Management Function (SMF) for K8s.

# Usage

```bash
juju deploy mongodb-k8s --channel 6/stable --trust
juju deploy sdcore-smf-k8s --channel=1.6/edge
juju deploy sdcore-nrf-k8s --channel=1.6/edge
juju deploy self-signed-certificates
juju deploy sdcore-nms-k8s --channel=1.6/edge
juju integrate sdcore-nms-k8s:common_database mongodb-k8s:database
juju integrate sdcore-nms-k8s:auth_database mongodb-k8s:database
juju integrate sdcore-nms-k8s:certificates self-signed-certificates:certificates
juju integrate sdcore-smf-k8s:default-database mongodb-k8s
juju integrate sdcore-nrf-k8s:certificates self-signed-certificates:certificates
juju integrate sdcore-nrf-k8s:sdcore_config sdcore-nms-k8s:sdcore_config
juju integrate sdcore-smf-k8s:fiveg_nrf sdcore-nrf-k8s:fiveg_nrf
juju integrate sdcore-smf-k8s:certificates self-signed-certificates:certificates
juju integrate sdcore-smf-k8s:sdcore_config sdcore-nms-k8s:sdcore_config
```

# Image

**smf**: `ghcr.io/canonical/sdcore-smf:2.0.2`

