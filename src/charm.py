#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G SMF service for K8s."""


import logging
from ipaddress import IPv4Address
from subprocess import check_output
from typing import Optional

from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires  # type: ignore[import]
from charms.loki_k8s.v1.loki_push_api import LogForwarder  # type: ignore[import]
from charms.prometheus_k8s.v0.prometheus_scrape import (  # type: ignore[import]  # noqa: E501
    MetricsEndpointProvider,
)
from charms.sdcore_nrf_k8s.v0.fiveg_nrf import NRFRequires  # type: ignore[import]
from charms.tls_certificates_interface.v3.tls_certificates import (  # type: ignore[import]
    CertificateExpiringEvent,
    TLSCertificatesRequiresV3,
    generate_csr,
    generate_private_key,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, Port, WaitingStatus

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/smf"
CONFIG_FILE = "smfcfg.yaml"
UEROUTING_CONFIG_FILE = "uerouting.yaml"
DATABASE_NAME = "sdcore_smf"
SMF_SBI_PORT = 29502
PFCP_PORT = 8805
PROMETHEUS_PORT = 9089
CERTS_DIR_PATH = "/support/TLS"  # The certs directory is hardcoded in the SMF code.
PRIVATE_KEY_NAME = "smf.key"
CSR_NAME = "smf.csr"
CERTIFICATE_NAME = "smf.pem"
CERTIFICATE_COMMON_NAME = "smf.sdcore"
LOGGING_RELATION_NAME = "logging"


class SMFOperatorCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to preform if we're removing the
            # charm.
            self.unit.status = BlockedStatus("Scaling is not implemented for this charm")
            return
        self._container_name = self._service_name = "smf"
        self._container = self.unit.get_container(self._container_name)
        self._nrf_requires = NRFRequires(charm=self, relation_name="fiveg_nrf")
        self._database = DatabaseRequires(
            self, relation_name="database", database_name=DATABASE_NAME
        )
        self._logging = LogForwarder(charm=self, relation_name=LOGGING_RELATION_NAME)
        self.unit.set_ports(
            PROMETHEUS_PORT,
            SMF_SBI_PORT,
            Port(port=PFCP_PORT, protocol="udp"),
        )
        self._metrics_endpoint = MetricsEndpointProvider(
            self,
            jobs=[
                {
                    "static_configs": [{"targets": [f"*:{PROMETHEUS_PORT}"]}],
                }
            ],
        )
        self._certificates = TLSCertificatesRequiresV3(self, "certificates")

        self.framework.observe(self.on.update_status, self._configure_sdcore_smf)
        self.framework.observe(self.on.smf_pebble_ready, self._configure_sdcore_smf)
        self.framework.observe(self.on.database_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self.on.database_relation_broken, self._on_database_relation_broken)
        self.framework.observe(self._database.on.database_created, self._configure_sdcore_smf)
        self.framework.observe(self.on.fiveg_nrf_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._configure_sdcore_smf)
        self.framework.observe(self._nrf_requires.on.nrf_broken, self._on_nrf_broken)
        self.framework.observe(self.on.certificates_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(
            self.on.certificates_relation_broken, self._on_certificates_relation_broken
        )
        self.framework.observe(
            self._certificates.on.certificate_available, self._configure_sdcore_smf
        )
        self.framework.observe(
            self._certificates.on.certificate_expiring, self._on_certificate_expiring
        )

    def _missing_mandatory_relations(self) -> Optional[str]:
        """Returns whether a mandatory Juju relation is missing.

        Returns:
            str: Missing mandatory relation.
        """
        for relation in ["database", "fiveg_nrf", "certificates"]:
            if not self._relation_created(relation):
                return relation
        return None

    def _configure_sdcore_smf(self, event: EventBase) -> None:  # noqa C901
        """Adds pebble layer and manages Juju unit status.

        Args:
            event: Juju event
        """
        if missing_relation := self._missing_mandatory_relations():
            self.unit.status = BlockedStatus(
                f"Waiting for `{missing_relation}` relation to be created"
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
            return
        if not _get_pod_ip():
            self.unit.status = WaitingStatus("Waiting for pod IP address to be available")
            return
        if not self._ue_config_file_is_written():
            self._write_ue_config_file()
        if not self._private_key_is_stored():
            self._generate_private_key()
        if not self._csr_is_stored():
            self._request_new_certificate()

        provider_certificate = self._get_current_provider_certificate()
        if not provider_certificate:
            self.unit.status = WaitingStatus("Waiting for certificates to be stored")
            return
        certificate_changed = self._update_certificate(provider_certificate=provider_certificate)
        config_file_changed = self._update_config_file()
        self._configure_pebble(restart=(config_file_changed or certificate_changed))
        self.unit.status = ActiveStatus()

    def _on_nrf_broken(self, event: EventBase) -> None:
        """Event handler for NRF relation broken.

        Args:
            event (NRFBrokenEvent): Juju event
        """
        self.unit.status = BlockedStatus("Waiting for fiveg_nrf relation")

    def _on_database_relation_broken(self, event: EventBase) -> None:
        """Event handler for database relation broken.

        Args:
            event: Juju event
        """
        self.unit.status = BlockedStatus("Waiting for database relation")

    def _on_certificates_relation_broken(self, event: EventBase) -> None:
        """Deletes TLS related artifacts and reconfigures workload."""
        if not self._container.can_connect():
            event.defer()
            return
        self._delete_private_key()
        self._delete_csr()
        self._delete_certificate()
        self.unit.status = BlockedStatus("Waiting for certificate relation")

    def _get_current_provider_certificate(self) -> str | None:
        """Compares the current certificate request to what is in the interface.

        Returns the current valid provider certificate if present
        """
        csr = self._get_stored_csr()
        for provider_certificate in self._certificates.get_assigned_certificates():
            if provider_certificate.csr == csr:
                return provider_certificate.certificate
        return None

    def _update_certificate(self, provider_certificate) -> bool:
        """Compares the provided certificate to what is stored.

        Returns True if the certificate was updated
        """
        existing_certificate = (
            self._get_stored_certificate() if self._certificate_is_stored() else ""
        )

        if existing_certificate != provider_certificate:
            self._store_certificate(certificate=provider_certificate)
            return True
        return False

    def _on_certificate_expiring(self, event: CertificateExpiringEvent) -> None:
        """Requests new certificate."""
        if not self._container.can_connect():
            event.defer()
            return
        if event.certificate != self._get_stored_certificate():
            logger.debug("Expiring certificate is not the one stored")
            return
        self._request_new_certificate()

    def _generate_private_key(self) -> None:
        """Generates and stores private key."""
        private_key = generate_private_key()
        self._store_private_key(private_key)

    def _request_new_certificate(self) -> None:
        """Generates and stores CSR, and uses it to request a new certificate."""
        private_key = self._get_stored_private_key()
        csr = generate_csr(
            private_key=private_key,
            subject=CERTIFICATE_COMMON_NAME,
            sans_dns=[CERTIFICATE_COMMON_NAME],
        )
        self._store_csr(csr)
        self._certificates.request_certificate_creation(certificate_signing_request=csr)

    def _delete_private_key(self) -> None:
        """Removes private key from workload."""
        if not self._private_key_is_stored():
            return
        self._container.remove_path(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")
        logger.info("Removed private key from workload")

    def _delete_csr(self) -> None:
        """Deletes CSR from workload."""
        if not self._csr_is_stored():
            return
        self._container.remove_path(path=f"{CERTS_DIR_PATH}/{CSR_NAME}")
        logger.info("Removed CSR from workload")

    def _delete_certificate(self) -> None:
        """Deletes certificate from workload."""
        if not self._certificate_is_stored():
            return
        self._container.remove_path(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")
        logger.info("Removed certificate from workload")

    def _private_key_is_stored(self) -> bool:
        """Returns whether private key is stored in workload."""
        return self._container.exists(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")

    def _csr_is_stored(self) -> bool:
        """Returns whether CSR is stored in workload."""
        return self._container.exists(path=f"{CERTS_DIR_PATH}/{CSR_NAME}")

    def _get_stored_certificate(self) -> str:
        """Returns stored certificate."""
        return str(self._container.pull(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}").read())

    def _get_stored_csr(self) -> str:
        """Returns stored CSR."""
        return str(self._container.pull(path=f"{CERTS_DIR_PATH}/{CSR_NAME}").read())

    def _get_stored_private_key(self) -> bytes:
        """Returns stored private key."""
        return str(
            self._container.pull(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}").read()
        ).encode()

    def _certificate_is_stored(self) -> bool:
        """Returns whether certificate is stored in workload."""
        return self._container.exists(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")

    def _store_certificate(self, certificate: str) -> None:
        """Stores certificate in workload."""
        self._container.push(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}", source=certificate)
        logger.info("Pushed certificate pushed to workload")

    def _store_private_key(self, private_key: bytes) -> None:
        """Stores private key in workload."""
        self._container.push(
            path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            source=private_key.decode(),
        )
        logger.info("Pushed private key to workload")

    def _store_csr(self, csr: bytes) -> None:
        """Stores CSR in workload."""
        self._container.push(path=f"{CERTS_DIR_PATH}/{CSR_NAME}", source=csr.decode().strip())
        logger.info("Pushed CSR to workload")

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
            scheme="https",
            tls_key_path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            tls_certificate_path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}",
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
        scheme: str,
        tls_key_path: str,
        tls_certificate_path: str,
    ) -> str:
        """Renders the config file content.

        Args:
            database_url (str): Database URL.
            database_name (str): SMF database name.
            smf_url (str): SMF URL.
            smf_sbi_port (int): SMF SBI port.
            nrf_url (str): NRF URL.
            pod_ip (IPv4Address): Pod IP address.
            scheme (str): SBI Interface scheme ("http" or "https")
            tls_key_path (str): Path to the TLS private key
            tls_certificate_path (str): Path to the TLS certificate path

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
            scheme=scheme,
            tls_key_path=tls_key_path,
            tls_certificate_path=tls_certificate_path,
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
