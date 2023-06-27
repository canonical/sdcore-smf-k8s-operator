<div align="center">
  <img src="./icon.svg" alt="ONF Icon" width="200" height="200">
</div>
<br/>
<div align="center">
  <a href="https://charmhub.io/sdcore-smf"><img src="https://charmhub.io/sdcore-smf/badge.svg" alt="CharmHub Badge"></a>
  <a href="https://github.com/canonical/sdcore-smf-operator/actions/workflows/publish-charm.yaml">
    <img src="https://github.com/canonical/sdcore-smf-operator/actions/workflows/publish-charm.yaml/badge.svg?branch=main" alt=".github/workflows/publish-charm.yaml">
  </a>
  <br/>
  <br/>
  <h1>SD-Core SMF Operator</h1>
</div>

Charmed Operator for the SD-Core Session Management Function (SMF).

# Usage

```bash
juju deploy mongodb-k8s --channel 5/edge --trust
juju deploy sdcore-smf --channel edge --trust
juju deploy sdcore-nrf --channel edge --trust
juju integrate sdcore-smf:default-database mongodb-k8s
juju integrate sdcore-smf:smf-database mongodb-k8s
juju integrate sdcore-smf:fiveg_nrf sdcore-nrf
```

### Optional

```bash
juju deploy self-signed-certificates --channel=edge
juju integrate sdcore-smf:certificates self-signed-certificates:certificates
```

# Image

**smf**: `ghcr.io/canonical/sdcore-smf:1.3`
