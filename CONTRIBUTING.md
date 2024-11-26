# Contributing
To make contributions to this charm, you'll need a working Juju development setup.

## Prerequisites
Install Charmcraft and LXD:
```shell
sudo snap install --classic charmcraft
sudo snap install lxd
sudo adduser $USER lxd
newgrp lxd
lxd init --auto
```

Install MicroK8s:
```shell
sudo snap install microk8s --channel=1.31-strict/stable
sudo usermod -a -G snap_microk8s $USER
newgrp snap_microk8s
sudo microk8s enable hostpath-storage
```

Install Juju and bootstrap a controller on the MicroK8S instance:
```shell
sudo snap install juju --channel=3.5/stable
juju bootstrap microk8s
```

This project uses `uv`. You can install it on Ubuntu with:

```shell
sudo snap install --classic astral-uv
```

You can create an environment for development with `uv`:

```shell
uv sync
source .venv/bin/activate
```

## Testing
This project uses `tox` for managing test environments. It can be installed
with:

```shell
uv tool install tox --with tox-uv
```

There are some pre-configured environments
that can be used for linting and formatting code when you're preparing contributions to the charm:

```shell
tox -e lint                                             # code style
tox -e static                                           # static analysis
tox -e unit                                             # unit tests
tox -e integration -- --charm_path=PATH_TO_BUILD_CHARM  # integration tests
```

```note
Integration tests require the charm to be built with `charmcraft pack` first.
```

## Build
Go to the charm directory and run:
```bash
charmcraft pack
```
