#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G SMF service."""

import logging
from typing import Union

from charms.data_platform_libs.v0.data_interfaces import (  # type: ignore[import]
    DatabaseCreatedEvent,
    DatabaseRequires,
)

# TODO: create the project and publish the lib
from charms.nrf_operator.v0.nrf import (  # type: ignore[import]  # noqa: E501
    NRFAvailableEvent,
    NRFRequires,
)
from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]  # noqa: E501
    KubernetesServicePatch,
)
from charms.prometheus_k8s.v0.prometheus_scrape import (  # type: ignore[import]  # noqa: E501
    MetricsEndpointProvider,
)
from jinja2 import Environment, FileSystemLoader
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/smf"
CONFIG_FILE_NAME = "smfcfg.yaml"
UE_CONFIG_FILE = "uerouting.yaml"
DATABASE_NAME = "free5gc"
SMF_DATABASE_NAME = "sdcore_smf"
SMF_SBI_PORT = 29502
PFCP_PORT = 8805
PROMETHEUS_PORT = 9089


class SMFOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "smf"
        self._container = self.unit.get_container(self._container_name)

        # NRF relation endpoint
        self._nrf_requires = NRFRequires(charm=self, relationship_name="nrf")

        # Databases libraries
        self._default_database = DatabaseRequires(
            self, relation_name="database", database_name=DATABASE_NAME
        )
        self._smf_database = DatabaseRequires(
            self, relation_name="smf-database", database_name=SMF_DATABASE_NAME
        )

        # Basic hooks
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.smf_pebble_ready, self._configure_sdcore_smf)

        # Database Hooks
        self.framework.observe(self.on.database_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(
            self._default_database.on.database_created, self._configure_sdcore_smf
        )
        self.framework.observe(self.on.smf_database_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._smf_database.on.database_created, self._configure_sdcore_smf)

        # NRF Hooks
        self.framework.observe(self.on.nrf_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._configure_sdcore_smf)

        # Kubernetes service patch
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="pfcp", port=PFCP_PORT, protocol="UDP"),
                ServicePort(name="sbi", port=SMF_SBI_PORT),
                ServicePort(name="prometheus-exporter", port=PROMETHEUS_PORT),
            ],
        )

        # Metrics endpoint
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}],
                }
            ],
        )

    def _on_install(self, event: InstallEvent) -> None:
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self._write_ue_config_file()

    def _configure_sdcore_smf(
        self, event: Union[PebbleReadyEvent, DatabaseCreatedEvent, NRFAvailableEvent]
    ) -> None:
        """Adds pebble layer and manages Juju unit status.

        Args:
            event: Juju PebbleReadyEvent event
        """
        if not self._default_database_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for default database relation to be created")
            return
        if not self._smf_database_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for SMF database relation to be created")
            return
        if not self._nrf_relation_is_created:
            self.unit.status = BlockedStatus("Waiting for NRF relation to be created")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._default_database_is_available:
            self.unit.status = WaitingStatus(
                "Waiting for default database relation to be available"
            )
            return
        if not self._smf_database_is_available:
            self.unit.status = WaitingStatus("Waiting for SMF database relation to be available")
            return
        if not self._nrf_is_available:
            self.unit.status = WaitingStatus("Waiting for NRF relation to be available")
            return
        # TODO: Outsource to separate function for handling database creted event.
        if not self._config_file_is_written:
            self._write_config_file(database_url=event.uris.split(",")[0], nrf_url=event.url)  # type: ignore[union-attr] # noqa: E501 TODO: remove.
        if not self._ue_config_file_is_written:
            self.unit.status = WaitingStatus("Waiting for UE config file to be written")
            return
        self._configure_pebble()

    def _configure_pebble(self) -> None:
        """Adds layer to pebble config if the proposed config is different from the current one."""
        self._container.add_layer("smf", self._pebble_layer, combine=True)
        self._container.replan()
        self.unit.status = ActiveStatus()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Writes config file to workload container and configures pebble.

        Args:
            event: DatabaseCreatedEvent
        """
        if not self._container.can_connect():
            event.defer()
            return
        self._write_config_file(
            database_url=event.uris.split(",")[0],
        )
        self._configure_sdcore_smf(event)

    def _write_config_file(self, database_url: str, nrf_url: str) -> None:
        """Writes config file to workload.

        Args:
            database_url (str): Database URL
            nrf_url (str): NRF URL
        """
        jinja2_env = Environment(loader=FileSystemLoader("src/templates"))
        template = jinja2_env.get_template("smfcfg.yaml.j2")
        # TODO: Fix config file params to write.
        content = template.render(
            nrf_url=nrf_url,
            smf_sbi_port=SMF_SBI_PORT,
            default_databadefault_database_namese_url=DATABASE_NAME,
            default_database_url=database_url,
            # pod_id=self._pod_id,  # type: ignore[attr-defined] # noqa: E501 TODO: remove.
        )
        self._container.push(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}", source=content)
        logger.info(f"Pushed: {CONFIG_FILE_NAME} to workload.")

    def _write_ue_config_file(self) -> None:
        with open(f"src/{UE_CONFIG_FILE}", "r") as f:
            content = f.read()

        logger.warning(f"########## Content ##########:\n\n{content}\n\n#################")
        self._container.push(path=f"{BASE_CONFIG_PATH}/{UE_CONFIG_FILE}", source=content)
        logger.info(f"Pushed {UE_CONFIG_FILE} config file to workload")

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    @property
    def _config_file_is_written(self) -> bool:
        """Returns whether the config file was written to the workload container.

        Returns:
            bool: Whether the config file was written.
        """
        if not self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE_NAME}"):
            logger.info(f"Config file is not written: {CONFIG_FILE_NAME}")
            return False
        logger.info("Config file is written")
        return True

    @property
    def _ue_config_file_is_written(self) -> bool:
        if not self._container.exists(f"{BASE_CONFIG_PATH}/{UE_CONFIG_FILE}"):
            logger.info(f"Config file is not written: {UE_CONFIG_FILE}")
            return False
        logger.info("Config file is written")
        return True

    @property
    def _default_database_relation_is_created(self) -> bool:
        """Returns whether database relation is created.

        Returns:
            bool: Whether database relation is created.
        """
        return self._relation_created("database")

    @property
    def _smf_database_relation_is_created(self) -> bool:
        """Returns whether database relation is created.

        Returns:
            bool: Whether database relation is created.
        """
        return self._relation_created("smf-database")

    @property
    def _nrf_relation_is_created(self) -> bool:
        """Returns whether database relation is created.

        Returns:
            bool: Whether database relation is created.
        """
        return self._relation_created("nrf")

    @property
    def _nrf_is_available(self) -> bool:
        """Returns whether the NRF endpoint is available.

        Returns:
            bool: whether the NRF endpoint is available.
        """
        if not self._nrf_requires.get_nrf_url():
            logger.info("NRF endpoint is not available")
            return False
        return True

    @property
    def _default_database_is_available(self) -> bool:
        """Returns whether database relation is available.

        Returns:
            bool: Whether database relation is available.
        """
        if not self._default_database.is_resource_created():
            logger.info("Default database is not available")
            return False
        return True

    @property
    def _smf_database_is_available(self) -> bool:
        """Returns whether database relation is available.

        Returns:
            bool: Whether database relation is available.
        """
        if not self._smf_database.is_resource_created():
            logger.info("SMF database is not available")
            return False
        return True

    @property
    def _pebble_layer(self):
        """Return a dictionary representing a Pebble layer.

        Returns:
            dict: Pebble layer
        """
        return {
            "summary": "smf layer",
            "description": "pebble config layer for smf",
            "services": {
                "smf": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": f"/free5gc/smf/smf -smfcfg {BASE_CONFIG_PATH}/{CONFIG_FILE_NAME} "
                    "-uerouting {BASE_CONFIG_PATH}/{UE_CONFIG_FILE_NAME}",
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
        }

    @property
    def _smf_hostname(self) -> str:
        return f"{self.model.app.name}.{self.model.name}.svc.cluster.local"


if __name__ == "__main__":  # pragma: nocover
    main(SMFOperatorCharm)
