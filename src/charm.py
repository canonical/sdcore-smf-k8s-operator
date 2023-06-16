#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G SMF service."""


import logging
from ipaddress import IPv4Address
from subprocess import check_output
from typing import Optional

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires  # type: ignore[import]
from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]  # noqa: E501
    KubernetesServicePatch,
)
from charms.prometheus_k8s.v0.prometheus_scrape import (  # type: ignore[import]  # noqa: E501
    MetricsEndpointProvider,
)
from charms.sdcore_nrf.v0.fiveg_nrf import NRFRequires  # type: ignore[import]
from jinja2 import Environment, FileSystemLoader
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, InstallEvent
from ops.framework import EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/smf"
CONFIG_FILE = "smfcfg.yaml"
UEROUTING_CONFIG_FILE = "uerouting.yaml"
DATABASE_NAME = "sdcore_smf"
SMF_SBI_PORT = 29502
PFCP_PORT = 8805
PROMETHEUS_PORT = 9089


class SMFOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "smf"
        self._container = self.unit.get_container(self._container_name)

        self._nrf_requires = NRFRequires(charm=self, relation_name="fiveg_nrf")

        self._database = DatabaseRequires(
            self, relation_name="database", database_name=DATABASE_NAME
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.smf_pebble_ready, self._configure_sdcore_smf)
        self.framework.observe(self.on.database_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._database.on.database_created, self._configure_sdcore_smf)

        self.framework.observe(self.on.fiveg_nrf_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._configure_sdcore_smf)

        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="pfcp", port=PFCP_PORT, protocol="UDP"),
                ServicePort(name="sbi", port=SMF_SBI_PORT),
                ServicePort(name="prometheus-exporter", port=PROMETHEUS_PORT),
            ],
        )

        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}],
                }
            ],
        )

    def _on_install(self, event: InstallEvent) -> None:
        """Handles the install event.

        Args:
            event (InstallEvent): Juju event.
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._storage_is_attached():
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            event.defer()
            return
        self._write_ue_config_file()

    def _configure_sdcore_smf(self, event: EventBase) -> None:
        """Adds pebble layer and manages Juju unit status.

        Args:
            event: Juju event
        """
        for relation in ["database", "fiveg_nrf"]:
            if not self._relation_created(relation):
                self.unit.status = BlockedStatus(
                    f"Waiting for `{relation}` relation to be created"
                )
                return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            return
        if not self._database_is_available():
            self.unit.status = WaitingStatus("Waiting for `database` relation to be available")
            return
        if not self._nrf_is_available():
            self.unit.status = WaitingStatus("Waiting for NRF relation to be available")
            return
        if not self._storage_is_attached():
            self.unit.status = WaitingStatus("Waiting for storage to be attached")
            event.defer()
            return
        if not _get_pod_ip():
            self.unit.status = WaitingStatus("Waiting for pod IP address to be available")
            event.defer()
            return
        if not self._ue_config_file_is_written():
            event.defer()
            self.unit.status = WaitingStatus(
                f"Waiting for `{UEROUTING_CONFIG_FILE}` config file to be pushed to workload container"  # noqa: W505, E501
            )
            return
        if self._update_config_file():
            self._configure_pebble(restart=True)
        else:
            self._configure_pebble()
        self.unit.status = ActiveStatus()

    def _configure_pebble(self, restart=False) -> None:
        """Configures the Pebble layer.

        Args:
            restart (bool): Whether to restart the SMF container.
        """
        self._container.add_layer("smf", self._pebble_layer, combine=True)
        if restart:
            self._container.restart(self._service_name)
            return
        self._container.replan()

    def _update_config_file(self) -> bool:
        """Updates config file.

        Writes the config file if it does not exist or
        the content does not match.

        Returns: True if config file was updated, False otherwise.
        """
        content = self._render_config_file(
            database_url=self._get_database_data()["uris"].split(",")[0],
            database_name=DATABASE_NAME,
            smf_url=self._smf_hostname,
            smf_sbi_port=SMF_SBI_PORT,
            nrf_url=self._nrf_requires.nrf_url,
            pod_ip=_get_pod_ip(),  # type: ignore[arg-type]
        )
        if not self._config_file_is_written() or not self._config_file_content_matches(
            content=content
        ):
            self._write_config_file(content=content)
            return True
        return False

    def _write_config_file(self, content: str) -> None:
        """Writes config file to workload.

        Args:
            content (str): Config file content.
        """
        self._container.push(
            path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE}", source=content, make_dirs=True
        )
        logger.info("Pushed: %s to workload.", CONFIG_FILE)

    def _write_ue_config_file(self) -> None:
        """Writes UE config file to workload."""
        with open(f"src/{UEROUTING_CONFIG_FILE}", "r") as f:
            content = f.read()

        self._container.push(
            path=f"{BASE_CONFIG_PATH}/{UEROUTING_CONFIG_FILE}", source=content, make_dirs=True
        )
        logger.info("Pushed %s config file to workload", UEROUTING_CONFIG_FILE)

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    def _storage_is_attached(self) -> bool:
        """Returns whether storage is attached to the workload container.

        Returns:
            bool: Whether storage is attached.
        """
        return self._container.exists(path=BASE_CONFIG_PATH)

    def _config_file_is_written(self) -> bool:
        """Returns whether the config file was written to the workload container.

        Returns:
            bool: Whether the config file was written.
        """
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE}"))

    @staticmethod
    def _render_config_file(
        *,
        database_url: str,
        database_name: str,
        smf_url: str,
        smf_sbi_port: int,
        nrf_url: str,
        pod_ip: str,
    ) -> str:
        """Renders the config file content.

        Args:
            database_url (str): Database URL.
            database_name (str): SMF database name.
            smf_url (str): SMF URL.
            smf_sbi_port (int): SMF SBI port.
            nrf_url (str): NRF URL.
            pod_ip (IPv4Address): Pod IP address.

        Returns:
            str: Config file content.
        """
        jinja2_env = Environment(loader=FileSystemLoader("src/templates"))
        template = jinja2_env.get_template("smfcfg.yaml.j2")
        return template.render(
            database_url=database_url,
            database_name=database_name,
            smf_url=smf_url,
            smf_sbi_port=smf_sbi_port,
            nrf_url=nrf_url,
            pod_ip=pod_ip,
        )

    def _config_file_content_matches(self, content: str) -> bool:
        """Returns whether the config file content matches the provided content.

        Returns:
            bool: Whether the config file content matches
        """
        existing_content = self._container.pull(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE}")
        return existing_content.read() == content

    def _ue_config_file_is_written(self) -> bool:
        """Returns whether the config file was written to the workload container.

        Returns:
            bool: Whether the config file was written.
        """
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{UEROUTING_CONFIG_FILE}"))

    def _nrf_is_available(self) -> bool:
        """Returns whether the NRF endpoint is available.

        Returns:
            bool: whether the NRF endpoint is available.
        """
        return bool(self._nrf_requires.nrf_url)

    def _database_is_available(self) -> bool:
        """Returns whether database relation is available.

        Returns:
            bool: Whether database relation is available.
        """
        return bool(self._database.is_resource_created())

    def _get_database_data(self) -> dict:
        """Returns the database data.

        Returns:
            dict: The database data.

        Raises:
            RuntimeError: If the database is not available.
        """
        if not self._database_is_available():
            raise RuntimeError("SMF database is not available")
        return self._database.fetch_relation_data()[self._database.relations[0].id]

    @property
    def _pebble_layer(self) -> dict:
        """Return a dictionary representing a Pebble layer.

        Returns:
            dict: Pebble layer
        """
        return {
            "summary": "smf layer",
            "description": "pebble config layer for smf",
            "services": {
                self._service_name: {
                    "override": "replace",
                    "startup": "enabled",
                    "command": f"/bin/smf -smfcfg {BASE_CONFIG_PATH}/{CONFIG_FILE} "
                    f"-uerouting {BASE_CONFIG_PATH}/{UEROUTING_CONFIG_FILE}",
                    "environment": self._environment_variables,
                }
            },
        }

    @property
    def _environment_variables(self) -> dict:
        """Returns workload container environment variables.

        Returns:
            dict: environment variables
        """
        return {
            "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
            "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
            "GRPC_TRACE": "all",
            "GRPC_VERBOSITY": "debug",
            "PFCP_PORT_UPF": "8805",
            "MANAGED_BY_CONFIG_POD": "true",
            "POD_IP": _get_pod_ip(),
        }

    @property
    def _smf_hostname(self) -> str:
        """Get the hostname of the Kubernetes pod.

        Returns:
            str: hostname of the Kubernetes pod.
        """
        return f"{self.model.app.name}.{self.model.name}.svc.cluster.local"


def _get_pod_ip() -> Optional[str]:
    """Returns the pod IP using juju client.

    Returns:
        str: The pod IP.
    """
    ip_address = check_output(["unit-get", "private-address"])
    return str(IPv4Address(ip_address.decode().strip())) if ip_address else None


if __name__ == "__main__":  # pragma: nocover
    main(SMFOperatorCharm)
