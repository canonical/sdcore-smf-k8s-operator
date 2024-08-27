# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import PropertyMock, patch

import pytest
import scenario

from charm import SMFOperatorCharm


class SMFUnitTestFixtures:
    patcher_sdcore_config_webui_url = patch(
        "charms.sdcore_nms_k8s.v0.sdcore_config.SdcoreConfigRequires.webui_url",
        new_callable=PropertyMock,
    )
    patcher_get_assigned_certificates = patch(
        "charms.tls_certificates_interface.v3.tls_certificates.TLSCertificatesRequiresV3.get_assigned_certificates"
    )
    patcher_generate_private_key = patch("charm.generate_private_key")
    patcher_generate_csr = patch("charm.generate_csr")
    patcher_nrf_url = patch("charm.NRFRequires.nrf_url", new_callable=PropertyMock)
    patcher_check_output = patch("charm.check_output")
    patcher_db_is_resource_created = patch(
        "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.is_resource_created"
    )
    patcher_db_fetch_relation_data = patch(
        "charms.data_platform_libs.v0.data_interfaces.DatabaseRequires.fetch_relation_data"
    )

    @pytest.fixture(autouse=True)
    def setup(self, request):
        self.mock_sdcore_config_webui_url = (
            SMFUnitTestFixtures.patcher_sdcore_config_webui_url.start()
        )
        self.mock_get_assigned_certificates = (
            SMFUnitTestFixtures.patcher_get_assigned_certificates.start()
        )
        self.mock_nrf_url = SMFUnitTestFixtures.patcher_nrf_url.start()
        self.mock_check_output = SMFUnitTestFixtures.patcher_check_output.start()
        self.mock_generate_private_key = SMFUnitTestFixtures.patcher_generate_private_key.start()
        self.mock_generate_csr = SMFUnitTestFixtures.patcher_generate_csr.start()
        self.mock_db_is_resource_created = (
            SMFUnitTestFixtures.patcher_db_is_resource_created.start()
        )
        self.mock_db_fetch_relation_data = (
            SMFUnitTestFixtures.patcher_db_fetch_relation_data.start()
        )
        yield
        request.addfinalizer(self.teardown)

    @staticmethod
    def teardown() -> None:
        patch.stopall()

    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=SMFOperatorCharm,
        )
