# SD-Core SMF Operator (k8s)
[![CharmHub Badge](https://charmhub.io/sdcore-smf/badge.svg)](https://charmhub.io/sdcore-smf)

Charmed Operator for the SD-Core Session Management Function (SMF).

# Usage

```bash
juju deploy mongodb-k8s --channel 5/edge --trust
juju deploy sdcore-smf --channel edge
juju deploy sdcore-nrf --channel edge
juju deploy self-signed-certificates --channel=beta
juju integrate sdcore-smf:default-database mongodb-k8s
juju integrate sdcore-smf:smf-database mongodb-k8s
juju integrate sdcore-nrf:certificates self-signed-certificates:certificates
juju integrate sdcore-smf:fiveg_nrf sdcore-nrf
juju integrate sdcore-smf:certificates self-signed-certificates:certificates
```

# Image

**smf**: `ghcr.io/canonical/sdcore-smf:1.3`
