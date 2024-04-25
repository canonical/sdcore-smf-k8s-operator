# SD-Core SMF Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-smf-k8s/badge.svg)](https://charmhub.io/sdcore-smf-k8s)

Charmed Operator for the SD-Core Session Management Function (SMF) for K8s.

# Usage

```bash
juju deploy mongodb-k8s --channel 6/beta --trust
juju deploy sdcore-smf-k8s --channel=1.5/edge
juju deploy sdcore-nrf-k8s --channel=1.5/edge
juju deploy self-signed-certificates
juju integrate sdcore-smf-k8s:default-database mongodb-k8s
juju integrate sdcore-smf-k8s:smf-database mongodb-k8s
juju integrate sdcore-nrf-k8s:certificates self-signed-certificates:certificates
juju integrate sdcore-smf-k8s:fiveg_nrf sdcore-nrf-k8s:fiveg_nrf
juju integrate sdcore-smf-k8s:certificates self-signed-certificates:certificates
```

# Image

**smf**: `ghcr.io/canonical/sdcore-smf:1.4.0`

