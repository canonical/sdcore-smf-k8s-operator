# Copyright 2023 Canonical
# See LICENSE file for licensing details.

import logging
import unittest
from unittest.mock import Mock, PropertyMock, patch

import yaml
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import SMFOperatorCharm

logger = logging.getLogger(__name__)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.namespace = "whatever"
        self.database_application_name = "mongodb-k8s"
        self.metadata = self._get_metadata()
        self.container_name = list(self.metadata["containers"].keys())[0]
        self.harness = testing.Harness(SMFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()

    @staticmethod
    def _get_metadata() -> dict:
        """Reads `metadata.yaml` and returns it as a dictionary.

        Returns:
            dics: metadata.yaml as a dictionary.
        """
        with open("metadata.yaml", "r") as f:
            data = yaml.safe_load(f)
        return data

    @staticmethod
    def _read_file(path: str) -> str:
        """Reads a file and returns as a string.

        Args:
            path (str): path to the file.

        Returns:
            str: content of the file.
        """
        with open(path, "r") as f:
            content = f.read()

        return content

    def _create_database_relation(self) -> int:
        """Creates SMF database relation.

        Returns:
            int: relation id.
        """
        relation_id = self.harness.add_relation(
            relation_name="database", remote_app=self.database_application_name
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{self.database_application_name}/0"
        )
        return relation_id

    def _create_nrf_relation(self) -> int:
        """Creates NRF relation.

        Returns:
            int: relation id.
        """
        relation_id = self.harness.add_relation(
            relation_name="fiveg_nrf", remote_app="nrf-operator"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="nrf-operator/0")
        return relation_id

    def _create_database_relation_and_populate_data(self) -> int:
        database_url = "http://6.5.6.5"
        database_username = "rock"
        database_password = "paper"
        database_relation_id = self._create_database_relation()
        self.harness.update_relation_data(
            relation_id=database_relation_id,
            app_or_unit=self.database_application_name,
            key_values={
                "username": database_username,
                "password": database_password,
                "uris": "".join([database_url]),
            },
        )
        return database_relation_id

    def test_given_container_cant_connect_when_on_install_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container=self.container_name, val=False)

        self.harness.charm._on_install(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    def test_given_container_can_connect_and_storage_is_attached_when_on_install_then_ue_config_file_is_written_to_workload_container(  # noqa: E501
        self,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.set_can_connect(container=self.container_name, val=True)
        root = self.harness.get_filesystem_root(self.container_name)

        self.harness.charm._on_install(event=Mock())

        expected_config_file_content = self._read_file("src/uerouting.yaml")

        self.assertEqual(
            (root / "etc/smf/uerouting.yaml").read_text(), expected_config_file_content
        )

    def test_given_container_can_connect_and_storage_is_not_attached_when_on_install_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_install(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for storage to be attached"),
        )

    def test_given_database_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for `database` relation to be created"),
        )

    def test_given_nrf_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self._create_database_relation()

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for `fiveg_nrf` relation to be created"),
        )

    def test_given_certificates_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self._create_database_relation()
        self._create_nrf_relation()

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for `certificates` relation to be created"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("charm.check_output")
    def test_given_smf_charm_in_active_status_when_nrf_relation_breaks_then_status_is_blocked(
        self, patch_check_output, patch_nrf_url
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        self._create_database_relation_and_populate_data()
        nrf_relation_id = self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_check_output.return_value = b"1.1.1.1"
        patch_nrf_url.return_value = "http://nrf.com:8080"
        self.harness.container_pebble_ready(self.container_name)

        self.harness.remove_relation(nrf_relation_id)

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for fiveg_nrf relation"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("charm.check_output")
    def test_given_smf_charm_in_active_status_when_database_relation_breaks_then_status_is_blocked(
        self, patch_check_output, patch_nrf_url
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        database_relation_id = self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_check_output.return_value = b"1.1.1.1"
        patch_nrf_url.return_value = "http://nrf.com:8080"
        self.harness.container_pebble_ready(self.container_name)

        self.harness.remove_relation(database_relation_id)

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for database relation"),
        )

    def test_given_container_cant_connect_when_configure_sdcore_smf_is_called_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_database_relation()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=False)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    def test_given_database_relation_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_database_relation()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for `database` relation to be available"),
        )

    def test_given_nrf_is_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for NRF relation to be available"),
        )

    @patch("charm.check_output")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    def test_given_ue_config_file_is_not_written_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
        patch_nrf_url,
        patch_check_output,
    ):
        self.harness.add_storage("config", attach=True)
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        patch_check_output.return_value = b"1.1.1.1"
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus(
                "Waiting for `uerouting.yaml` config file to be pushed to workload container"
            ),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    def test_given_storage_is_not_attached_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self, patch_nrf_url
    ):
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf.com:8080"
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for storage to be attached"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("charm.check_output")
    def test_given_ip_not_available_when_configure_then_status_is_waiting(
        self,
        patch_check_output,
        patch_nrf_url,
    ):
        self.harness.add_storage("config", attach=True)
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.charm._certificate_is_stored = Mock(return_value=True)
        patch_check_output.return_value = b""
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for pod IP address to be available"),
        )

    @patch("charm.check_output")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    def test_given_certificate_is_not_stored_when_configure_sdcore_smf_then_status_is_waiting(  # noqa: E501
        self,
        patch_nrf_url,
        patch_check_output,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf.com:8080"
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.charm._storage_is_attached = Mock(return_value=True)
        self.harness.charm._ue_config_file_is_written = Mock(return_value=True)
        self.harness.charm._certificate_is_stored = Mock(return_value=False)
        patch_check_output.return_value = b"1.1.1.1"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for certificates to be stored")
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("charm.check_output")
    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_status_is_active(  # noqa: E501
        self,
        patch_check_output,
        patch_nrf_url,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_check_output.return_value = b"1.1.1.1"
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus(),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("charm.check_output")
    def test_given_nrf_is_available_when_database_is_created_then_config_file_is_written_with_expected_content(  # noqa: E501
        self,
        patch_check_output,
        patch_nrf_url,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            (root / "etc/smf/smfcfg.yaml").read_text(),
            self._read_file("tests/unit/expected_smfcfg.yaml"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("charm.check_output")
    def test_given_config_file_exists_and_is_not_changed_when_configure_smf_then_config_file_is_not_re_written_with_same_content(  # noqa: E501
        self,
        patch_check_output,
        patch_nrf_url,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        (root / "etc/smf/smfcfg.yaml").write_text(
            self._read_file("tests/unit/expected_smfcfg.yaml")
        )
        config_modification_time = (root / "etc/smf/smfcfg.yaml").stat().st_mtime
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        patch_nrf_url.return_value = "http://nrf.com:8080"
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual((root / "etc/smf/smfcfg.yaml").stat().st_mtime, config_modification_time)

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("charm.check_output")
    def test_given_config_file_exists_and_is_changed_when_configure_smf_then_config_file_is_updated(  # noqa: E501
        self,
        patch_check_output,
        patch_nrf_url,
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        (root / "etc/smf/smfcfg.yaml").write_text("super different config file content")
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            (root / "etc/smf/smfcfg.yaml").read_text(),
            self._read_file("tests/unit/expected_smfcfg.yaml"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("charm.check_output")
    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_expected_plan_is_applied(  # noqa: E501
        self, patch_check_output, patch_nrf_url
    ):
        self.harness.add_storage("config", attach=True)
        self.harness.add_storage("certs", attach=True)
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.pem").write_text(certificate)
        (root / "etc/smf/uerouting.yaml").write_text(self._read_file("src/uerouting.yaml"))
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        self._create_database_relation_and_populate_data()
        self._create_nrf_relation()
        self.harness.add_relation(
            relation_name="certificates", remote_app="tls-certificates-operator"
        )
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf:8000"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        expected_plan = {
            "services": {
                self.container_name: {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "/bin/smf -smfcfg /etc/smf/smfcfg.yaml "
                    "-uerouting /etc/smf/uerouting.yaml",
                    "environment": {
                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                        "GRPC_TRACE": "all",
                        "GRPC_VERBOSITY": "debug",
                        "PFCP_PORT_UPF": "8805",
                        "POD_IP": pod_ip,
                        "MANAGED_BY_CONFIG_POD": "true",
                    },
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan(self.container_name).to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("charm.generate_private_key")
    def test_given_can_connect_when_on_certificates_relation_created_then_private_key_is_generated(
        self, patch_generate_private_key
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        private_key = b"whatever key content"
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_generate_private_key.return_value = private_key

        self.harness.charm._on_certificates_relation_created(event=Mock)

        self.assertEqual((root / "support/TLS/smf.key").read_text(), private_key.decode())

    def test_given_certificates_are_stored_when_on_certificates_relation_broken_then_certificates_are_removed(  # noqa: E501
        self,
    ):
        self.harness.add_storage("certs", attach=True)
        private_key = "whatever key content"
        csr = "Whatever CSR content"
        certificate = "Whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.key").write_text(private_key)
        (root / "support/TLS/smf.csr").write_text(csr)
        (root / "support/TLS/smf.pem").write_text(certificate)
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificates_relation_broken(event=Mock)

        with self.assertRaises(FileNotFoundError):
            (root / "support/TLS/smf.key").read_text()
        with self.assertRaises(FileNotFoundError):
            (root / "support/TLS/smf.pem").read_text()
        with self.assertRaises(FileNotFoundError):
            (root / "support/TLS/smf.csr").read_text()

    @patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation",  # noqa: E501
        new=Mock,
    )
    @patch("charm.generate_csr")
    def test_given_private_key_exists_when_on_certificates_relation_joined_then_csr_is_generated(
        self, patch_generate_csr
    ):
        self.harness.add_storage("certs", attach=True)
        private_key = "whatever key content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.key").write_text(private_key)
        csr = b"whatever csr content"
        patch_generate_csr.return_value = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificates_relation_joined(event=Mock)

        self.assertEqual((root / "support/TLS/smf.csr").read_text(), csr.decode())

    @patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation",  # noqa: E501
    )
    @patch("charm.generate_csr")
    def test_given_private_key_exists_and_cert_not_yet_requested_when_on_certificates_relation_joined_then_cert_is_requested(  # noqa: E501
        self,
        patch_generate_csr,
        patch_request_certificate_creation,
    ):
        self.harness.add_storage("certs", attach=True)
        private_key = "whatever key content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.key").write_text(private_key)
        csr = b"whatever csr content"
        patch_generate_csr.return_value = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificates_relation_joined(event=Mock)

        patch_request_certificate_creation.assert_called_with(certificate_signing_request=csr)

    @patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation",  # noqa: E501
    )
    def test_given_cert_already_stored_when_on_certificates_relation_joined_then_cert_is_not_requested(  # noqa: E501
        self, patch_request_certificate_creation
    ):
        self.harness.add_storage("certs", attach=True)
        private_key = "whatever key content"
        certificate = "whatever certificate content"
        root = self.harness.get_filesystem_root(self.container_name)
        (root / "support/TLS/smf.key").write_text(private_key)
        (root / "support/TLS/smf.pem").write_text(certificate)
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificates_relation_joined(event=Mock)

        patch_request_certificate_creation.assert_not_called()

    def test_given_csr_matches_stored_one_when_certificate_available_then_certificate_is_pushed(
        self,
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        csr = "Whatever CSR content"
        (root / "support/TLS/smf.csr").write_text(csr)
        certificate = "Whatever certificate content"
        event = Mock()
        event.certificate = certificate
        event.certificate_signing_request = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_available(event=event)

        self.assertEqual((root / "support/TLS/smf.pem").read_text(), certificate)

    def test_given_csr_doesnt_match_stored_one_when_certificate_available_then_certificate_is_not_pushed(  # noqa: E501
        self,
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        csr = "Stored CSR content"
        (root / "support/TLS/smf.csr").write_text(csr)
        certificate = "Whatever certificate content"
        event = Mock()
        event.certificate = certificate
        event.certificate_signing_request = "Relation CSR content (different from stored one)"
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_available(event=event)

        with self.assertRaises(FileNotFoundError):
            (root / "support/TLS/smf.pem").read_text()

    @patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation",  # noqa: E501
    )
    @patch("charm.generate_csr")
    def test_given_certificate_does_not_match_stored_one_when_certificate_expiring_then_certificate_is_not_requested(  # noqa: E501
        self, patch_generate_csr, patch_request_certificate_creation
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        certificate = "Stored certificate content"
        (root / "support/TLS/smf.pem").write_text(certificate)
        event = Mock()
        event.certificate = "Relation certificate content (different from stored)"
        csr = b"whatever csr content"
        patch_generate_csr.return_value = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_expiring(event=event)

        patch_request_certificate_creation.assert_not_called()

    @patch(
        "charms.tls_certificates_interface.v2.tls_certificates.TLSCertificatesRequiresV2.request_certificate_creation",  # noqa: E501
    )
    @patch("charm.generate_csr")
    def test_given_certificate_matches_stored_one_when_certificate_expiring_then_certificate_is_requested(  # noqa: E501
        self, patch_generate_csr, patch_request_certificate_creation
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        private_key = "whatever key content"
        certificate = "whatever certificate content"
        (root / "support/TLS/smf.key").write_text(private_key)
        (root / "support/TLS/smf.pem").write_text(certificate)
        event = Mock()
        event.certificate = certificate
        csr = b"whatever csr content"
        patch_generate_csr.return_value = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_expiring(event=event)

        patch_request_certificate_creation.assert_called_with(certificate_signing_request=csr)
