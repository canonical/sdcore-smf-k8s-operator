#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed operator for the 5G SMF service for K8s."""

import logging
from ipaddress import IPv4Address
from subprocess import check_output
from typing import List, Optional

from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.prometheus_k8s.v0.prometheus_scrape import (
    MetricsEndpointProvider,
)
from charms.sdcore_nms_k8s.v0.sdcore_config import (
    SdcoreConfigRequires,
)
from charms.sdcore_nrf_k8s.v0.fiveg_nrf import NRFRequires
from charms.tls_certificates_interface.v4.tls_certificates import (
    Certificate,
    CertificateRequest,
    PrivateKey,
    TLSCertificatesRequiresV4,
)
from jinja2 import Environment, FileSystemLoader
from ops import ActiveStatus, BlockedStatus, CollectStatusEvent, ModelError, Port, WaitingStatus
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.main import main
from ops.pebble import Layer

logger = logging.getLogger(__name__)

BASE_CONFIG_PATH = "/etc/smf"
CONFIG_FILE = "smfcfg.yaml"
UEROUTING_CONFIG_FILE = "uerouting.yaml"
SMF_SBI_PORT = 29502
PFCP_PORT = 8805
PROMETHEUS_PORT = 9089
CERTS_DIR_PATH = "/support/TLS"  # The certs directory is hardcoded in the SMF code.
PRIVATE_KEY_NAME = "smf.key"
CERTIFICATE_NAME = "smf.pem"
CERTIFICATE_COMMON_NAME = "smf.sdcore"
LOGGING_RELATION_NAME = "logging"
FIVEG_NRF_RELATION_NAME = "fiveg_nrf"
SDCORE_CONFIG_RELATION_NAME = "sdcore_config"
TLS_RELATION_NAME = "certificates"
WORKLOAD_VERSION_FILE_NAME = "/etc/workload-version"


class SMFOperatorCharm(CharmBase):
    """Main class to describe juju event handling for the SD-Core SMF operator for K8s."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to perform if we're removing the
            # charm.
            return
        self._container_name = self._service_name = "smf"
        self._container = self.unit.get_container(self._container_name)
        self._nrf_requires = NRFRequires(charm=self, relation_name=FIVEG_NRF_RELATION_NAME)
        self._webui_requires = SdcoreConfigRequires(
            charm=self, relation_name=SDCORE_CONFIG_RELATION_NAME
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
        self._certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name=TLS_RELATION_NAME,
            certificate_requests=[self._get_certificate_request()],
        )
        self.framework.observe(self.on.update_status, self._configure_sdcore_smf)
        self.framework.observe(self.on.smf_pebble_ready, self._configure_sdcore_smf)
        self.framework.observe(self.on.fiveg_nrf_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self._nrf_requires.on.nrf_available, self._configure_sdcore_smf)
        self.framework.observe(
            self._webui_requires.on.webui_url_available,
            self._configure_sdcore_smf,
        )
        self.framework.observe(self.on.sdcore_config_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(self.on.certificates_relation_joined, self._configure_sdcore_smf)
        self.framework.observe(
            self.on.certificates_relation_broken, self._on_certificates_relation_broken
        )
        self.framework.observe(
            self._certificates.on.certificate_available, self._configure_sdcore_smf
        )

    def _configure_sdcore_smf(self, _) -> None:
        """Handle Juju events.

        This event handler is called for every event that affects the charm state
        (ex. configuration files, relation data). This method performs a couple of checks
        to make sure that the workload is ready to be started. Then, it configures the SMF
        workload and runs the Pebble services.

        Args:
            _ (EventBase): Juju event
        """
        if not self.ready_to_configure():
            logger.info("The preconditions for the configuration are not met yet.")
            return

        if not self._ue_config_file_is_written():
            self._write_ue_config_file()

        if not self._certificate_is_available():
            logger.info("The certificate is not available yet.")
            return

        certificate_update_required = self._check_and_update_certificate()

        desired_config_file = self._generate_smf_config_file()
        if config_update_required := self._is_config_update_required(desired_config_file):
            self._push_config_file(content=desired_config_file)

        should_restart = config_update_required or certificate_update_required
        self._configure_pebble(restart=should_restart)

    def _on_collect_unit_status(self, event: CollectStatusEvent):  # noqa C901
        """Check the unit status and set to Unit when CollectStatusEvent is fired.

        Also sets the unit workload version if present
        Args:
            event: CollectStatusEvent
        """
        if not self.unit.is_leader():
            # NOTE: In cases where leader status is lost before the charm is
            # finished processing all teardown events, this prevents teardown
            # event code from running. Luckily, for this charm, none of the
            # teardown code is necessary to perform if we're removing the
            # charm.
            event.add_status(BlockedStatus("Scaling is not implemented for this charm"))
            logger.info("Scaling is not implemented for this charm")
            return

        if missing_relations := self._missing_relations():
            event.add_status(
                BlockedStatus(f"Waiting for {', '.join(missing_relations)} relation(s)")
            )
            logger.info("Waiting for %s  relation(s)", ", ".join(missing_relations))
            return

        if not self._container.can_connect():
            event.add_status(WaitingStatus("Waiting for container to be ready"))
            logger.info("Waiting for container to be ready")
            return

        self.unit.set_workload_version(self._get_workload_version())

        if not self._nrf_is_available():
            event.add_status(WaitingStatus("Waiting for NRF relation to be available"))
            logger.info("Waiting for NRF relation to be available")
            return

        if not self._webui_data_is_available:
            event.add_status(WaitingStatus("Waiting for Webui data to be available"))
            logger.info("Waiting for Webui data to be available")
            return

        if not self._storage_is_attached():
            event.add_status(WaitingStatus("Waiting for storage to be attached"))
            logger.info("Waiting for storage to be attached")
            return

        if not _get_pod_ip():
            event.add_status(WaitingStatus("Waiting for pod IP address to be available"))
            logger.info("Waiting for pod IP address to be available")
            return

        if not self._certificate_is_available():
            event.add_status(WaitingStatus("Waiting for certificates to be available"))
            logger.info("Waiting for certificates to be available")

        if not self._smf_service_is_running():
            event.add_status(WaitingStatus("Waiting for SMF service to start"))
            logger.info("Waiting for SMF service to start")
            return

        event.add_status(ActiveStatus())

    def _smf_service_is_running(self) -> bool:
        """Check if the SMF service is running.

        Returns:
            bool: Whether the SMF service is running.
        """
        if not self._container.can_connect():
            return False
        try:
            service = self._container.get_service(self._service_name)
        except ModelError:
            return False
        return service.is_running()

    def ready_to_configure(self) -> bool:
        """Return whether the preconditions are met to proceed with the configuration.

        Returns:
            ready_to_configure: True if all conditions are met else False
        """
        if not self._container.can_connect():
            return False

        if self._missing_relations():
            return False

        if not self._nrf_is_available():
            return False

        if not self._webui_data_is_available:
            return False

        if not self._storage_is_attached():
            return False

        if not _get_pod_ip():
            return False

        return True

    def _check_and_update_certificate(self) -> bool:
        """Check if the certificate or private key needs an update and perform the update.

        This method retrieves the currently assigned certificate and private key associated with
        the charm's TLS relation. It checks whether the certificate or private key has changed
        or needs to be updated. If an update is necessary, the new certificate or private key is
        stored.

        Returns:
            bool: True if either the certificate or the private key was updated, False otherwise.
        """
        provider_certificate, private_key = self._certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request()
        )
        if not provider_certificate or not private_key:
            logger.debug("Certificate or private key is not available")
            return False
        if certificate_update_required := self._is_certificate_update_required(
            provider_certificate.certificate
        ):
            self._store_certificate(certificate=provider_certificate.certificate)
        if private_key_update_required := self._is_private_key_update_required(private_key):
            self._store_private_key(private_key=private_key)
        return certificate_update_required or private_key_update_required

    @staticmethod
    def _get_certificate_request() -> CertificateRequest:
        return CertificateRequest(
            common_name=CERTIFICATE_COMMON_NAME,
            sans_dns=frozenset([CERTIFICATE_COMMON_NAME]),
        )

    def _missing_relations(self) -> List[str]:
        """Return list of missing relations.

        If all the relations are created, it returns an empty list.

        Returns:
            list: missing relation names.
        """
        missing_relations = []
        for relation in [
            FIVEG_NRF_RELATION_NAME,
            TLS_RELATION_NAME,
            SDCORE_CONFIG_RELATION_NAME,
        ]:
            if not self._relation_created(relation):
                missing_relations.append(relation)
        return missing_relations

    @property
    def _webui_data_is_available(self) -> bool:
        return bool(self._webui_requires.webui_url)

    def _push_config_file(
        self,
        content: str,
    ) -> None:
        """Push the SMF config file to the container.

        Args:
            content (str): Content of the config file.
        """
        self._container.push(
            path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE}", source=content, make_dirs=True
        )
        logger.info("Pushed: %s to workload.", CONFIG_FILE)

    def _is_config_update_required(self, content: str) -> bool:
        """Decide whether config update is required by checking existence and config content.

        Args:
            content (str): desired config file content

        Returns:
            True if config update is required else False
        """
        if not self._config_file_is_written() or not self._config_file_content_matches(
            content=content
        ):
            return True
        return False

    def _generate_smf_config_file(self) -> str:
        """Handle creation of the SMF config file based on a given template.

        Returns:
            content (str): desired config file content
        """
        if not self._nrf_requires.nrf_url:
            return ""
        if not (pod_ip := _get_pod_ip()):
            return ""
        if not self._webui_requires.webui_url:
            return ""
        return self._render_config_file(
            smf_url=self._smf_hostname,
            smf_sbi_port=SMF_SBI_PORT,
            nrf_url=self._nrf_requires.nrf_url,
            pod_ip=pod_ip,
            scheme="https",
            tls_key_path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            tls_certificate_path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}",
            webui_uri=self._webui_requires.webui_url,
        )

    def _is_certificate_update_required(self, certificate: Certificate) -> bool:
        return self._get_existing_certificate() != certificate

    def _is_private_key_update_required(self, private_key: PrivateKey) -> bool:
        return self._get_existing_private_key() != private_key

    def _get_existing_certificate(self) -> Optional[Certificate]:
        return self._get_stored_certificate() if self._certificate_is_stored() else None

    def _get_existing_private_key(self) -> Optional[PrivateKey]:
        return self._get_stored_private_key() if self._private_key_is_stored() else None

    def _on_certificates_relation_broken(self, event: EventBase) -> None:
        """Delete TLS related artifacts and reconfigures workload."""
        if not self._container.can_connect():
            event.defer()
            return
        self._delete_private_key()
        self._delete_certificate()

    def _certificate_is_available(self) -> bool:
        cert, key = self._certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request()
        )
        return bool(cert and key)

    def _delete_private_key(self) -> None:
        """Remove private key from workload."""
        if not self._private_key_is_stored():
            return
        self._container.remove_path(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")
        logger.info("Removed private key from workload")

    def _delete_certificate(self) -> None:
        """Delete certificate from workload."""
        if not self._certificate_is_stored():
            return
        self._container.remove_path(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")
        logger.info("Removed certificate from workload")

    def _private_key_is_stored(self) -> bool:
        """Return whether private key is stored in workload."""
        return self._container.exists(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")

    def _get_stored_certificate(self) -> Certificate:
        cert_string = str(self._container.pull(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}").read())
        return Certificate.from_string(cert_string)

    def _get_stored_private_key(self) -> PrivateKey:
        key_string = str(self._container.pull(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}").read())
        return PrivateKey.from_string(key_string)

    def _certificate_is_stored(self) -> bool:
        """Return whether certificate is stored in workload."""
        return self._container.exists(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")

    def _store_certificate(self, certificate: Certificate) -> None:
        """Store certificate in workload."""
        self._container.push(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}", source=str(certificate))
        logger.info("Pushed certificate to workload")

    def _store_private_key(self, private_key: PrivateKey) -> None:
        """Store private key in workload."""
        self._container.push(
            path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            source=str(private_key),
        )
        logger.info("Pushed private key to workload")

    def _get_workload_version(self) -> str:
        """Return the workload version.

        Checks for the presence of /etc/workload-version file
        and if present, returns the contents of that file. If
        the file is not present, an empty string is returned.

        Returns:
            string: A human-readable string representing the
            version of the workload
        """
        if self._container.exists(path=f"{WORKLOAD_VERSION_FILE_NAME}"):
            version_file_content = self._container.pull(
                path=f"{WORKLOAD_VERSION_FILE_NAME}"
            ).read()
            return version_file_content
        return ""

    def _configure_pebble(self, restart=False) -> None:
        """Configure and restart the workload if required.

        This method detects the changes between the Pebble layer and the Pebble services.
        If a change is detected, it applies the desired configuration.
        Then, it restarts the workload if a restart is required.

        Args:
            restart (bool): Whether to restart the SMF container.
        """
        plan = self._container.get_plan()
        if plan.services != self._pebble_layer.services:
            self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
            self._container.replan()
            logger.info("New layer added: %s", self._pebble_layer)
        if restart:
            self._container.restart(self._service_name)
            logger.info("Restarted container %s", self._service_name)
            return

    def _write_ue_config_file(self) -> None:
        """Write UE config file to workload."""
        with open(f"src/{UEROUTING_CONFIG_FILE}", "r") as f:
            content = f.read()

        self._container.push(
            path=f"{BASE_CONFIG_PATH}/{UEROUTING_CONFIG_FILE}", source=content, make_dirs=True
        )
        logger.info("Pushed %s config file to workload", UEROUTING_CONFIG_FILE)

    def _relation_created(self, relation_name: str) -> bool:
        """Return whether a given Juju relation was created.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    def _storage_is_attached(self) -> bool:
        return self._container.exists(path=BASE_CONFIG_PATH) and self._container.exists(
            path=CERTS_DIR_PATH
        )

    def _config_file_is_written(self) -> bool:
        """Return whether the config file was written to the workload container.

        Returns:
            bool: Whether the config file was written.
        """
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{CONFIG_FILE}"))

    @staticmethod
    def _render_config_file(
        *,
        smf_url: str,
        smf_sbi_port: int,
        nrf_url: str,
        pod_ip: str,
        scheme: str,
        tls_key_path: str,
        tls_certificate_path: str,
        webui_uri: str,
    ) -> str:
        """Render the config file content.

        Args:
            smf_url (str): SMF URL.
            smf_sbi_port (int): SMF SBI port.
            nrf_url (str): NRF URL.
            pod_ip (IPv4Address): Pod IP address.
            scheme (str): SBI Interface scheme ("http" or "https")
            tls_key_path (str): Path to the TLS private key
            tls_certificate_path (str): Path to the TLS certificate path
            webui_uri (str) : URL of the Webui.

        Returns:
            str: Config file content.
        """
        jinja2_env = Environment(loader=FileSystemLoader("src/templates"))
        template = jinja2_env.get_template("smfcfg.yaml.j2")
        return template.render(
            smf_url=smf_url,
            smf_sbi_port=smf_sbi_port,
            nrf_url=nrf_url,
            pod_ip=pod_ip,
            scheme=scheme,
            tls_key_path=tls_key_path,
            tls_certificate_path=tls_certificate_path,
            webui_uri=webui_uri,
        )

    def _config_file_content_matches(self, content: str) -> bool:
        """Return whether the config file content matches the provided content.

        Returns:
            bool: Whether the config file content matches
        """
        existing_content = self._container.pull(path=f"{BASE_CONFIG_PATH}/{CONFIG_FILE}")
        return existing_content.read() == content

    def _ue_config_file_is_written(self) -> bool:
        """Return whether the config file was written to the workload container.

        Returns:
            bool: Whether the config file was written.
        """
        return bool(self._container.exists(f"{BASE_CONFIG_PATH}/{UEROUTING_CONFIG_FILE}"))

    def _nrf_is_available(self) -> bool:
        """Return whether the NRF endpoint is available.

        Returns:
            bool: whether the NRF endpoint is available.
        """
        return bool(self._nrf_requires.nrf_url)

    @property
    def _pebble_layer(self) -> Layer:
        """Return a dictionary representing a Pebble layer.

        Returns:
            dict: Pebble layer
        """
        return Layer(
            {
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
        )

    @property
    def _environment_variables(self) -> dict:
        """Return workload container environment variables.

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
    """Return the pod IP using juju client.

    Returns:
        str: The pod IP.
    """
    ip_address = check_output(["unit-get", "private-address"])
    return str(IPv4Address(ip_address.decode().strip())) if ip_address else None


if __name__ == "__main__":  # pragma: nocover
    main(SMFOperatorCharm)
