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
  <h1>SD-CORE SMF Operator</h1>
</div>

Charmed Operator for the SD-CORE Session Management Function (SMF).

# Usage

```bash
juju deploy mongodb-k8s --channel 5/edge --trust
juju deploy sdcore-smf --channel edge --trust
juju deploy sdcore-nrf --channel edge --trust
juju relate sdcore-smf:default-database mongodb-k8s
juju relate sdcore-smf:smf-database mongodb-k8s
juju relate sdcore-smf:fiveg_nrf sdcore-nrf
```

# Image

**smf**: `omecproject/5gc-smf:master-13e5671`
