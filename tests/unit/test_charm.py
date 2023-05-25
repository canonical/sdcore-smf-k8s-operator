# Copyright 2023 Canonical
# See LICENSE file for licensing details.

import logging
import unittest
from io import StringIO
from unittest.mock import Mock, PropertyMock, patch

import yaml
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import SMFOperatorCharm

logger = logging.getLogger(__name__)


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        self.maxDiff = None
        self.namespace = "whatever"
        self.default_database_application_name = "mongodb-k8s"
        self.metadata = self._get_metadata()
        self.container_name = list(self.metadata["containers"].keys())[0]
        self.harness = testing.Harness(SMFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _get_metadata(self) -> dict:
        """Reads `metadata.yaml` and returns it as a dictionary.

        Returns:
            dics: metadata.yaml as a dictionary.
        """
        with open("metadata.yaml", "r") as f:
            data = yaml.safe_load(f)
        return data

    def _read_file(self, path: str) -> str:
        """Reads a file an returns as a string.

        Args:
            path (str): path to the file.

        Returns:
            str: content of the file.
        """
        with open(path, "r") as f:
            content = f.read()

        return content

    def _create_default_database_relation(self) -> int:
        """Creates database relation.

        Returns:
            int: relation id.
        """
        relation_id = self.harness.add_relation(
            relation_name="default-database", remote_app=self.default_database_application_name
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{self.default_database_application_name}/0"
        )
        return relation_id

    def _create_smf_database_relation(self) -> int:
        """Creates SMF database relation.

        Returns:
            int: relation id.
        """
        relation_id = self.harness.add_relation(
            relation_name="smf-database", remote_app=self.default_database_application_name
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name=f"{self.default_database_application_name}/0"
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

    def _database_is_available(self) -> str:
        database_url = "http://1.1.1.1"
        database_username = "banana"
        database_password = "pizza"
        database_relation_id = self._create_default_database_relation()
        self.harness.update_relation_data(
            relation_id=database_relation_id,
            app_or_unit=self.default_database_application_name,
            key_values={
                "username": database_username,
                "password": database_password,
                "uris": "".join([database_url]),
            },
        )
        return database_url

    def _smf_database_is_available(self) -> str:
        smf_database_url = "http://6.5.6.5"
        smf_database_username = "rock"
        smf_database_password = "paper"
        smf_database_relation_id = self._create_smf_database_relation()
        self.harness.update_relation_data(
            relation_id=smf_database_relation_id,
            app_or_unit=self.default_database_application_name,
            key_values={
                "username": smf_database_username,
                "password": smf_database_password,
                "uris": "".join([smf_database_url]),
            },
        )
        return smf_database_url

    def test_given_container_cant_connect_when_on_install_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container=self.container_name, val=False)

        self.harness.charm._on_install(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_container_can_connect_and_storage_is_attached_when_on_install_then_ue_config_file_is_written_to_workload_container(  # noqa: E501
        self, patch_push, patch_exists
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_exists.return_value = True

        self.harness.charm._on_install(event=Mock())

        expected_config_file_content = self._read_file("src/uerouting.yaml")
        patch_push.assert_called_with(
            path="/etc/smf/uerouting.yaml",
            source=expected_config_file_content,
            make_dirs=True,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_container_can_connect_and_storage_is_not_attached_when_on_install_then_status_is_waiting(  # noqa: E501
        self, patch_push, patch_exists
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_exists.return_value = False

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
            BlockedStatus("Waiting for `default-database` relation to be created"),
        )

    def test_given_smf_database_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self._create_default_database_relation()

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for `smf-database` relation to be created"),
        )

    def test_given_nrf_relation_not_created_when_configure_sdcore_smf_is_called_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self._create_default_database_relation()
        self._create_smf_database_relation()

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus("Waiting for `fiveg_nrf` relation to be created"),
        )

    def test_given_container_cant_connect_when_configure_sdcore_smf_is_called_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_default_database_relation()
        self._create_smf_database_relation()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=False)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    def test_given_database_relation_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_default_database_relation()
        self._create_smf_database_relation()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for `default-database` relation to be available"),
        )

    def test_given_smf_database_relation_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._database_is_available()
        self._create_smf_database_relation()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for `smf-database` relation to be available"),
        )

    def test_given_nrf_is_not_available_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for NRF relation to be available"),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("ops.model.Container.exists")
    def test_given_ue_config_file_is_not_written_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self,
        patch_exists,
        patch_nrf_url,
    ):
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_exists.side_effect = [True, False]
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus(
                "Waiting for `uerouting.yaml` config file to be pushed to workload container"
            ),
        )

    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("ops.model.Container.exists")
    def test_given_storage_is_not_attached_when_configure_sdcore_smf_is_called_then_status_is_waiting(  # noqa: E501
        self, patch_exists, patch_nrf_url
    ):
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_exists.return_value = [False]
        patch_nrf_url.return_value = "http://nrf.com:8080"

    @patch("ops.model.Container.pull")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("ops.model.Container.push")
    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_status_is_active(  # noqa: E501
        self, patch_exists, patch_check_output, patch_push, patch_nrf_url, patch_pull
    ):
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_exists.side_effect = [True, True, True]
        patch_check_output.return_value = b"1.1.1.1"
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status,
            ActiveStatus(),
        )

    @patch("ops.model.Container.pull")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("ops.model.Container.exists")
    @patch("charm.check_output")
    @patch("ops.model.Container.push")
    def test_given_nrf_is_available_when_database_is_created_then_config_file_is_written_with_expected_content(  # noqa: E501
        self,
        patch_push,
        patch_check_output,
        patch_exists,
        patch_nrf_url,
        patch_pull,
    ):
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container="smf", val=True)
        patch_exists.side_effect = [True, True, False]
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        patch_push.assert_called_with(
            path="/etc/smf/smfcfg.yaml",
            source=self._read_file("tests/unit/expected_smfcfg.yaml"),
            make_dirs=True,
        )

    @patch("ops.model.Container.pull")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("ops.model.Container.exists")
    @patch("charm.check_output")
    @patch("ops.model.Container.push")
    def test_given_config_file_exists_and_is_not_changed_when_configure_smf_then_config_file_is_not_re_written_with_same_content(  # noqa: E501
        self,
        patch_push,
        patch_check_output,
        patch_exists,
        patch_nrf_url,
        patch_pull,
    ):
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        patch_pull.return_value = StringIO(self._read_file("tests/unit/expected_smfcfg.yaml"))
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container="smf", val=True)
        patch_exists.side_effect = [True, True, True]
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        patch_push.assert_not_called()

    @patch("ops.model.Container.pull")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url", new_callable=PropertyMock)
    @patch("ops.model.Container.exists")
    @patch("charm.check_output")
    @patch("ops.model.Container.push")
    def test_given_config_file_exists_and_is_changed_when_configure_smf_then_config_file_is_updated(  # noqa: E501
        self,
        patch_push,
        patch_check_output,
        patch_exists,
        patch_nrf_url,
        patch_pull,
    ):
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        patch_pull.return_value = StringIO("super different config file content")
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container="smf", val=True)
        patch_exists.side_effect = [True, True, True]
        patch_nrf_url.return_value = "http://nrf.com:8080"

        self.harness.charm._configure_sdcore_smf(event=Mock())

        patch_push.assert_called_with(
            path="/etc/smf/smfcfg.yaml",
            source=self._read_file("tests/unit/expected_smfcfg.yaml"),
            make_dirs=True,
        )

    @patch("ops.model.Container.pull")
    @patch("charms.sdcore_nrf.v0.fiveg_nrf.NRFRequires.nrf_url")
    @patch("ops.model.Container.push")
    @patch("charm.check_output")
    @patch("ops.model.Container.exists")
    def test_given_config_files_and_relations_are_created_when_configure_sdcore_smf_is_called_then_expected_plan_is_applied(  # noqa: E501
        self, patch_exists, patch_check_output, patch_push, patch_nrf_url, patch_pull
    ):
        pod_ip = "1.1.1.1"
        patch_check_output.return_value = pod_ip.encode()
        self._database_is_available()
        self._smf_database_is_available()
        self._create_nrf_relation()
        self.harness.set_can_connect(container=self.container_name, val=True)
        patch_nrf_url.return_value = "http://nrf:8000"
        patch_exists.side_effect = [True, True, True]

        self.harness.charm._configure_sdcore_smf(event=Mock())

        expected_plan = {
            "services": {
                "smf": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "/free5gc/smf/smf -smfcfg /etc/smf/smfcfg.yaml "
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
