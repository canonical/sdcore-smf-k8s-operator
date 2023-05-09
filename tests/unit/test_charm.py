# Copyright 2023 Ubuntu
# See LICENSE file for licensing details.

import logging
import unittest
from unittest.mock import Mock, patch

import yaml
from ops import testing
from ops.model import WaitingStatus

from charm import SMFOperatorCharm

# TODO: load stuff from the metadata.yaml


logger = logging.getLogger(__name__)


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.metadata = self._get_metadata()
        self.container_name = list(self.metadata["containers"].keys())[0]
        self.harness = testing.Harness(SMFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def _create_database_relation(self) -> int:
        """Creates a database relation.

        Returns:
            int: relation id.
        """
        relation_id = self.harness.add_relation(relation_name="database", remote_app="mongodb-k8s")
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="mongodb-k8s/0")
        return relation_id

    def _get_metadata(self) -> dict:
        """Reads `metadata.yaml` and returns it as a dictionary.

        Returns:
            dics: metadata.yaml as a dictionary.
        """
        with open("metadata.yaml", "r") as f:
            data = yaml.safe_load(f)
        return data

    def _read_config_file(self, path: str) -> str:
        """Reads a file an returns as a string.

        Args:
            path (str): path to the file.

        Returns:
            str: content of the file.
        """
        with open(path, "r") as f:
            content = f.read()

        return content

    def test_given_container_cant_connect_when_on_install_then_status_is_waiting(
        self,
    ):
        self.harness.set_can_connect(container=self.container_name, val=False)

        self.harness.charm._on_install(event=Mock())

        self.assertEqual(
            self.harness.model.unit.status, WaitingStatus("Waiting for container to be ready")
        )

    @patch("ops.model.Container.push")
    def test_given_container_can_connect_when_on_install_then_ue_config_file_is_written_to_workload_container(  # noqa: E501
        self, patch_push
    ):
        self.harness.set_can_connect(container=self.container_name, val=True)

        self.harness.charm._on_install(event=Mock())

        expected_config_file_content = self._read_config_file("src/uerouting.yaml")
        patch_push.assert_called_with(
            path="/etc/smf/uerouting.yaml",
            source=expected_config_file_content,
        )

    # @patch("ops.model.Container.push")
    # def test_given_can_connect_to_workload_container_when_database_relation_created_event_then_config_wile_is_written(  # noqa: E501, W505
    #     self, patch_push
    # ):
    #     container_name = "smf"
    #     self.harness.set_can_connect(container=container_name, val=True)
    #     uri_0 = "1.2.3.4:1234"
    #     uri_1 = "5.6.7.8:1111"
    #     self.harness.set_can_connect(container=container_name, val=True)
    #     relation_data = {
    #         "username": "banana",
    #         "password": "password123",
    #         "uris": "".join([uri_0, ",", uri_1]),
    #     }
    #     relation_id = self._create_database_relation()

    #     self.harness.update_relation_data(
    #         relation_id=relation_id, app_or_unit="mongodb-k8s", key_values=relation_data
    #     )

    #     patch_push.assert_called_with(
    #         path="/etc/smf/smfcfg.yaml",
    #         source=f'configuration:\n  DefaultPlmnId:\n    mcc: "208"\n    mnc: "93"\n  MongoDBName: free5gc\n  MongoDBUrl: { uri_0 }\n  mongoDBStreamEnable: true\n  mongodb:\n    name: free5gc\n    url: { uri_0 }\n  nfKeepAliveTime: 60\n  nfProfileExpiryEnable: true\n  sbi:\n    bindingIPv4: 0.0.0.0\n    port: 29510\n    registerIPv4: nrf\n    scheme: http\n  serviceNameList:\n  - nnrf-nfm\n  - nnrf-disc\ninfo:\n  description: NRF initial local configuration\n  version: 1.0.0\nlogger:\n  AMF:\n    ReportCaller: false\n    debugLevel: info\n  AUSF:\n    ReportCaller: false\n    debugLevel: info\n  Aper:\n    ReportCaller: false\n    debugLevel: info\n  CommonConsumerTest:\n    ReportCaller: false\n    debugLevel: info\n  FSM:\n    ReportCaller: false\n    debugLevel: info\n  MongoDBLibrary:\n    ReportCaller: false\n    debugLevel: info\n  N3IWF:\n    ReportCaller: false\n    debugLevel: info\n  NAS:\n    ReportCaller: false\n    debugLevel: info\n  NGAP:\n    ReportCaller: false\n    debugLevel: info\n  NRF:\n    ReportCaller: false\n    debugLevel: info\n  NamfComm:\n    ReportCaller: false\n    debugLevel: info\n  NamfEventExposure:\n    ReportCaller: false\n    debugLevel: info\n  NsmfPDUSession:\n    ReportCaller: false\n    debugLevel: info\n  NudrDataRepository:\n    ReportCaller: false\n    debugLevel: info\n  OpenApi:\n    ReportCaller: false\n    debugLevel: info\n  PCF:\n    ReportCaller: false\n    debugLevel: info\n  PFCP:\n    ReportCaller: false\n    debugLevel: info\n  PathUtil:\n    ReportCaller: false\n    debugLevel: info\n  SMF:\n    ReportCaller: false\n    debugLevel: info\n  UDM:\n    ReportCaller: false\n    debugLevel: info\n  UDR:\n    ReportCaller: false\n    debugLevel: info\n  WEBUI:\n    ReportCaller: false\n    debugLevel: info',  # noqa: E501, W505
    #     )

    # def test_given_when_then(self):
    #     logger.warning(f"Charm name: {self.metadata.get('name')}")
    #     raise
