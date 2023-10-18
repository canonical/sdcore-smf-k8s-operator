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
sudo snap install microk8s --channel=1.27-strict/stable
sudo usermod -a -G snap_microk8s $USER
newgrp snap_microk8s
sudo microk8s enable hostpath-storage
```

Install Juju and bootstrap a controller on the MicroK8S instance:
```shell
sudo snap install juju --channel=3.1/stable
juju bootstrap microk8s
```

Install `pip` and `tox`:
```shell
sudo apt install python3-pip
python3 -m pip install "tox>=4.0.0"
```

## Development
Activate the virtual environment created by `tox` for development:
```shell
tox --notest -e unit
source .tox/unit/bin/activate
```

## Testing
This project uses `tox` for managing test environments.

There are some pre-configured environments
that can be used for linting and formatting code when you're preparing contributions to the charm:

```shell
tox -e lint          # code style
tox -e static        # static analysis
tox -e unit          # unit tests
tox -e integration   # integration tests
```

## Build
Go to the charm directory and run:
```bash
charmcraft pack
```
