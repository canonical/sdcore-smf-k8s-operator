# Copyright 2023 Canonical
# See LICENSE file for licensing details.

import logging
import os
from typing import Generator
from unittest.mock import Mock, PropertyMock, patch

import pytest
import yaml
from charm import SMFOperatorCharm
from charms.tls_certificates_interface.v3.tls_certificates import (  # type: ignore[import]
    ProviderCertificate,
)
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

logger = logging.getLogger(__name__)

DATABASE_URL = "http://6.5.6.5"
DATABASE_USERNAME = "rock"
DATABASE_PASSWORD = "paper"
DB_APPLICATION_NAME = "mongodb-k8s"
DB_RELATION_NAME = "database"
NRF_RELATION_NAME = "fiveg_nrf"
WEBUI_URL = "sdcore-webui:9876"
SDCORE_CONFIG_RELATION_NAME = "sdcore_config"
NMS_APPLICATION_NAME = "sdcore-nms-operator"
TLS_APPLICATION_NAME = "tls-certificates-operator"
TLS_RELATION_NAME = "certificates"
NAMESPACE = "whatever"
POD_IP = b"1.1.1.1"
VALID_NRF_URL = "https://nrf:443"
CERTIFICATES_LIB = (
    "charms.tls_certificates_interface.v3.tls_certificates.TLSCertificatesRequiresV3"
)
CERTIFICATE = "whatever certificate content"
CERTIFICATE_PATH = "support/TLS/smf.pem"
CSR = "whatever CSR content"
CSR_PATH = "support/TLS/smf.csr"
PRIVATE_KEY = "whatever key content"
PRIVATE_KEY_PATH = "support/TLS/smf.key"
CONFIG_FILE_PATH = "etc/smf/smfcfg.yaml"
EXPECTED_CONFIG_FILE_PATH = "tests/unit/expected_smfcfg.yaml"
UE_CONFIG_FILE_PATH = "etc/smf/uerouting.yaml"
EXPECTED_UE_CONFIG_FILE_PATH = "src/uerouting.yaml"


class TestCharm:
    patcher_check_output = patch("charm.check_output")
    patcher_nrf_url = patch(
        "charms.sdcore_nrf_k8s.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock
    )
    patcher_webui_url = patch(
        "charms.sdcore_nms_k8s.v0.sdcore_config.SdcoreConfigRequires.webui_url",
        new_callable=PropertyMock,
    )
    patcher_is_resource_created = patch(
        "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created"
    )
    patcher_generate_csr = patch("charm.generate_csr")
    patcher_generate_private_key = patch("charm.generate_private_key")
    patcher_get_assigned_certificates = patch(f"{CERTIFICATES_LIB}.get_assigned_certificates")  # noqa: E501
    patcher_request_certificate_creation = patch(
        f"{CERTIFICATES_LIB}.request_certificate_creation"
    )  # noqa: E501

    @pytest.fixture()
    def setup(self):
        self.mock_generate_csr = TestCharm.patcher_generate_csr.start()
        self.mock_generate_private_key = TestCharm.patcher_generate_private_key.start()
        self.mock_get_assigned_certificates = TestCharm.patcher_get_assigned_certificates.start()
        self.mock_request_certificate_creation = (
            TestCharm.patcher_request_certificate_creation.start()
        )  # noqa: E501
        self.mock_is_resource_created = TestCharm.patcher_is_resource_created.start()
        self.mock_nrf_url = TestCharm.patcher_nrf_url.start()
        self.mock_webui_url = TestCharm.patcher_webui_url.start()
        self.mock_check_output = TestCharm.patcher_check_output.start()
        metadata = self._get_metadata()
        self.container_name = list(metadata["containers"].keys())[0]

    @staticmethod
    def teardown() -> None:
        patch.stopall()

    @pytest.fixture()
    def mock_default_values(self):
        self.mock_nrf_url.return_value = VALID_NRF_URL
        self.mock_webui_url.return_value = WEBUI_URL
        self.mock_check_output.return_value = POD_IP
        self.mock_generate_private_key.return_value = PRIVATE_KEY.encode()
        self.mock_generate_csr.return_value = CSR.encode()

    @pytest.fixture(autouse=True)
    def harness(self, setup, request):
        self.harness = testing.Harness(SMFOperatorCharm)
        self.harness.set_model_name(name=NAMESPACE)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()
        yield self.harness
        self.harness.cleanup()
        request.addfinalizer(self.teardown)

    @pytest.fixture()
    def add_storage(self) -> None:
        self.harness.add_storage(storage_name="certs", attach=True)  # type:ignore
        self.harness.add_storage(storage_name="config", attach=True)  # type:ignore

    @staticmethod
    def _get_metadata() -> dict:
        """Read `charmcraft.yaml` and returns it as a dictionary."""
        with open("charmcraft.yaml", "r") as f:
            data = yaml.safe_load(f)
        return data

    @staticmethod
    def _read_file(path: str) -> str:
        """Read a file and returns as a string.

        Args:
            path (str): path to the file.

        Returns:
            str: content of the file.
        """
        with open(path, "r") as f:
            content = f.read()
        return content

    @staticmethod
    def _get_provider_certificate():
        provider_certificate = Mock(ProviderCertificate)
        provider_certificate.certificate = CERTIFICATE
        provider_certificate.csr = CSR
        return provider_certificate

    @pytest.fixture()
    def nrf_relation_id(self) -> Generator[int, None, None]:
        relation_id = self.harness.add_relation(  # type:ignore
            relation_name=NRF_RELATION_NAME, remote_app="nrf-operator"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="nrf-operator/0")  # type:ignore
        yield relation_id

    @pytest.fixture()
    def certificates_relation_id(self) -> Generator[int, None, None]:
        relation_id = self.harness.add_relation(  # type:ignore
            relation_name=TLS_RELATION_NAME, remote_app=TLS_APPLICATION_NAME
        )
        self.harness.add_relation_unit(  # type:ignore
            relation_id=relation_id, remote_unit_name=f"{TLS_APPLICATION_NAME}0"
        )
        yield relation_id

    @pytest.fixture()
    def sdcore_config_relation_id(self) -> Generator[int, None, None]:
        sdcore_config_relation_id = self.harness.add_relation(  # type:ignore
            relation_name=SDCORE_CONFIG_RELATION_NAME,
            remote_app=NMS_APPLICATION_NAME,
        )
        self.harness.add_relation_unit(  # type:ignore
            relation_id=sdcore_config_relation_id, remote_unit_name=f"{NMS_APPLICATION_NAME}/0"
        )
        self.harness.update_relation_data(  # type:ignore
            relation_id=sdcore_config_relation_id,
            app_or_unit=NMS_APPLICATION_NAME,
            key_values={
                "webui_url": WEBUI_URL,
            },
        )
        yield sdcore_config_relation_id

    @pytest.fixture()
    def database_relation_id(self) -> Generator[int, None, None]:
        relation_id = self.harness.add_relation(  # type:ignore
            relation_name=DB_RELATION_NAME,
            remote_app=DB_APPLICATION_NAME,
        )
        self.harness.add_relation_unit(  # type:ignore
            relation_id=relation_id,
            remote_unit_name=f"{DB_APPLICATION_NAME}/0",
        )
        yield relation_id

    def _create_database_relation_and_populate_data(self) -> int:
        """Create a database relation and set the database information.

        Returns:
            relation_id: ID of the created relation
        """
        database_relation_id = self.harness.add_relation(  # type:ignore
            relation_name=DB_RELATION_NAME,
            remote_app=DB_APPLICATION_NAME,
        )
        self.harness.update_relation_data(  # type:ignore
            relation_id=database_relation_id,
            app_or_unit=DB_APPLICATION_NAME,
            key_values={
                "username": DATABASE_USERNAME,
                "password": DATABASE_PASSWORD,
                "uris": "".join([DATABASE_URL]),
            },
        )
        return database_relation_id

    def test_given_container_can_connect_and_storage_is_attached_when_configure_sdcore_smf_is_called_then_ue_config_file_is_written_to_workload_container(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)
        root = self.harness.get_filesystem_root(self.container_name)
        self._create_database_relation_and_populate_data()

        self.harness.charm._configure_sdcore_smf(event=Mock())

        expected_config_file_content = self._read_file(EXPECTED_UE_CONFIG_FILE_PATH)

        assert (root / UE_CONFIG_FILE_PATH).read_text() == expected_config_file_content

    def test_given_database_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self, nrf_relation_id, sdcore_config_relation_id, certificates_relation_id
    ):
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for database relation(s)")

    def test_given_nrf_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self, database_relation_id, sdcore_config_relation_id, certificates_relation_id
    ):
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for fiveg_nrf relation(s)")

    def test_given_certificates_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self, nrf_relation_id, database_relation_id, sdcore_config_relation_id
    ):
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus(
            "Waiting for certificates relation(s)"
        )

    def test_given_sdcore_config_relation_not_created_when_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self, nrf_relation_id, certificates_relation_id, database_relation_id
    ):
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus(
            "Waiting for sdcore_config relation(s)"
        )

    def test_given_smf_charm_in_active_status_when_nrf_relation_breaks_then_status_is_blocked(
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self._create_database_relation_and_populate_data()
        self.harness.container_pebble_ready(self.container_name)

        self.harness.remove_relation(nrf_relation_id)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for fiveg_nrf relation(s)")

    def test_given_smf_charm_in_active_status_when_database_relation_breaks_then_status_is_blocked(
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        database_relation_id = self._create_database_relation_and_populate_data()
        self.harness.container_pebble_ready(self.container_name)

        self.harness.remove_relation(database_relation_id)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus("Waiting for database relation(s)")

    def test_given_smf_charm_in_active_status_when_sdcore_config_relation_breaks_then_status_is_blocked(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        database_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self.harness.remove_relation(sdcore_config_relation_id)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == BlockedStatus(
            "Waiting for sdcore_config relation(s)"
        )

    def test_given_container_cant_connect_when_configure_sdcore_smf_is_called_is_called_then_status_is_waiting(  # noqa: E501
        self,
        nrf_relation_id,
        database_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self.harness.set_can_connect(container=self.container_name, val=False)
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus("Waiting for container to be ready")

    def test_given_database_relation_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        database_relation_id,
        sdcore_config_relation_id,
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)
        self.mock_is_resource_created.return_value = False
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for `database` relation to be available"
        )

    def test_given_nrf_is_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self._create_database_relation_and_populate_data()
        self.harness.set_can_connect(container=self.container_name, val=True)
        self.mock_nrf_url.return_value = None
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for NRF relation to be available"
        )  # noqa: E501

    def test_given_webui_data_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
        mock_default_values,
    ):
        self._create_database_relation_and_populate_data()
        self.harness.set_can_connect(container=self.container_name, val=True)
        self.mock_webui_url.return_value = None
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for Webui data to be available"
        )  # noqa: E501

    @pytest.mark.parametrize(
        "storage_name",
        [
            "certs",
            "config",
        ],
    )
    def test_storage_is_not_attached_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self, nrf_relation_id, certificates_relation_id, storage_name, sdcore_config_relation_id
    ):
        self._create_database_relation_and_populate_data()
        self.harness.add_storage(storage_name=storage_name, attach=True)
        self.harness.set_can_connect(container=self.container_name, val=True)
        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()

        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for storage to be attached"
        )  # noqa: E501

    def test_given_ip_not_available_when_configure_then_status_is_waiting(
        self, add_storage, nrf_relation_id, certificates_relation_id, sdcore_config_relation_id
    ):
        self._create_database_relation_and_populate_data()
        self.harness.charm._certificate_is_stored = Mock(return_value=True)
        self.mock_check_output.return_value = b""

        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for pod IP address to be available"
        )  # noqa: E501

    def test_given_certificate_is_not_stored_when_configure_sdcore_smf_then_status_is_waiting(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)
        self._create_database_relation_and_populate_data()
        self.harness.charm._storage_is_attached = Mock(return_value=True)
        self.harness.charm._ue_config_file_is_written = Mock(return_value=True)
        self.harness.charm._certificate_is_stored = Mock(return_value=False)

        self.harness.charm._configure_sdcore_smf(event=Mock())
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == WaitingStatus(
            "Waiting for certificates to be stored"
        )  # noqa: E501

    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_status_is_active(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        self.mock_get_assigned_certificates.return_value = [self._get_provider_certificate()]
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / CSR_PATH).write_text(CSR)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self._create_database_relation_and_populate_data()

        self.harness.container_pebble_ready(self.container_name)
        self.harness.evaluate_status()
        assert self.harness.model.unit.status == ActiveStatus()

    def test_given_nrf_is_available_when_database_is_created_then_config_file_is_written_with_expected_content(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / CSR_PATH).write_text(CSR)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self._create_database_relation_and_populate_data()
        self.mock_get_assigned_certificates.return_value = [self._get_provider_certificate()]

        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        assert (root / CONFIG_FILE_PATH).read_text() == self._read_file(EXPECTED_CONFIG_FILE_PATH)

    def test_given_config_file_exists_and_is_not_changed_when_configure_smf_then_config_file_is_not_re_written_with_same_content(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        (root / CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_CONFIG_FILE_PATH))
        config_modification_time = (root / CONFIG_FILE_PATH).stat().st_mtime
        self._create_database_relation_and_populate_data()
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        assert (root / CONFIG_FILE_PATH).stat().st_mtime == config_modification_time

    def test_given_config_file_exists_and_is_changed_when_configure_smf_then_config_file_is_updated(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CSR_PATH).write_text(CSR)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        (root / CONFIG_FILE_PATH).write_text("super different config file content")
        self._create_database_relation_and_populate_data()
        self.mock_get_assigned_certificates.return_value = [self._get_provider_certificate()]
        self.harness.container_pebble_ready(self.container_name)

        assert (root / CONFIG_FILE_PATH).read_text() == self._read_file(EXPECTED_CONFIG_FILE_PATH)

    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_expected_plan_is_applied(  # noqa: E501
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        (root / CSR_PATH).write_text(CSR)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))

        self._create_database_relation_and_populate_data()
        self.mock_get_assigned_certificates.return_value = [self._get_provider_certificate()]
        self.harness.container_pebble_ready(self.container_name)

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
                        "POD_IP": POD_IP.decode(),
                        "MANAGED_BY_CONFIG_POD": "true",
                    },
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan(self.container_name).to_dict()
        assert expected_plan == updated_plan

    def test_given_can_connect_when_on_certificates_relation_created_then_private_key_is_generated(
        self,
        add_storage,
        mock_default_values,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self.harness.set_can_connect(container=self.container_name, val=True)
        csr = CSR.encode()
        self.mock_generate_csr.return_value = csr
        self._create_database_relation_and_populate_data()
        assert (root / PRIVATE_KEY_PATH).read_text() == PRIVATE_KEY

    def test_given_certificates_are_stored_when_on_certificates_relation_broken_then_certificates_are_removed(  # noqa: E501
        self,
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / CSR_PATH).write_text(CSR)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificates_relation_broken(event=Mock)

        with pytest.raises(FileNotFoundError):
            (root / PRIVATE_KEY_PATH).read_text()
        with pytest.raises(FileNotFoundError):
            (root / CERTIFICATE_PATH).read_text()
        with pytest.raises(FileNotFoundError):
            (root / CSR_PATH).read_text()

    def test_given_private_key_exists_when_on_certificates_relation_joined_then_csr_is_generated(
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        mock_default_values,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self.harness.set_can_connect(container=self.container_name, val=True)
        self._create_database_relation_and_populate_data()

        assert (root / CSR_PATH).read_text() == CSR

    def test_given_private_key_exists_and_cert_not_yet_requested_when_on_certificates_relation_joined_then_cert_is_requested(  # noqa: E501
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        mock_default_values,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self.harness.set_can_connect(container=self.container_name, val=True)
        self._create_database_relation_and_populate_data()

        self.mock_request_certificate_creation.assert_called_with(
            certificate_signing_request=CSR.encode()
        )

    def test_given_cert_already_stored_when_on_certificates_relation_joined_then_cert_is_not_requested(  # noqa: E501
        self, add_storage, mock_default_values
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.mock_request_certificate_creation.assert_not_called()

    def test_given_csr_matches_stored_one_when_certificate_available_then_certificate_is_pushed(
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        mock_default_values,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / CSR_PATH).write_text(CSR)
        (root / UE_CONFIG_FILE_PATH).write_text(self._read_file(EXPECTED_UE_CONFIG_FILE_PATH))
        self._create_database_relation_and_populate_data()

        self.mock_get_assigned_certificates.return_value = [self._get_provider_certificate()]
        self.harness.container_pebble_ready(self.container_name)

        assert (root / CERTIFICATE_PATH).read_text() == CERTIFICATE

    def test_given_csr_doesnt_match_stored_one_when_certificate_available_then_certificate_is_not_pushed(  # noqa: E501
        self,
        add_storage,
        nrf_relation_id,
        certificates_relation_id,
        mock_default_values,
        sdcore_config_relation_id,
    ):
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / CSR_PATH).write_text(CSR)

        provider_certificate = Mock(ProviderCertificate)
        provider_certificate.certificate = CERTIFICATE
        provider_certificate.csr = "Relation CSR content (different from stored one)"
        self.mock_get_assigned_certificates.return_value = [provider_certificate]

        self.harness.container_pebble_ready(self.container_name)

        with pytest.raises(FileNotFoundError):
            (root / CERTIFICATE_PATH).read_text()

    def test_given_certificate_does_not_match_stored_one_when_certificate_expiring_then_certificate_is_not_requested(  # noqa: E501
        self,
    ):
        self.harness.add_storage("certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        event = Mock()
        event.certificate = "Relation certificate content (different from stored)"
        csr = b"whatever csr content"
        self.mock_generate_csr.return_value = csr
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_expiring(event=event)

        self.mock_request_certificate_creation.assert_not_called()

    def test_given_certificate_matches_stored_one_when_certificate_expiring_then_certificate_is_requested(  # noqa: E501
        self,
    ):
        self.harness.add_storage(storage_name="certs", attach=True)
        root = self.harness.get_filesystem_root(self.container_name)
        (root / PRIVATE_KEY_PATH).write_text(PRIVATE_KEY)
        (root / CERTIFICATE_PATH).write_text(CERTIFICATE)
        event = Mock()
        event.certificate = CERTIFICATE
        self.mock_generate_csr.return_value = CSR.encode()
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_certificate_expiring(event=event)

        self.mock_request_certificate_creation.assert_called_with(
            certificate_signing_request=CSR.encode()
        )

    def test_given_no_workload_version_file_when_container_can_connect_then_workload_version_not_set(  # noqa: E501
        self,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self._create_database_relation_and_populate_data()
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.evaluate_status()
        version = self.harness.get_workload_version()
        assert version == ""

    def test_given_workload_version_file_when_container_can_connect_then_workload_version_set(
        self,
        nrf_relation_id,
        certificates_relation_id,
        sdcore_config_relation_id,
    ):
        self._create_database_relation_and_populate_data()
        expected_version = "1.2.3"
        root = self.harness.get_filesystem_root(self.container_name)
        os.mkdir(f"{root}/etc")
        (root / "etc/workload-version").write_text(expected_version)
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.evaluate_status()
        version = self.harness.get_workload_version()
        assert version == expected_version
