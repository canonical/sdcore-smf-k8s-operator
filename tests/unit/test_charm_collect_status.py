# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import tempfile

import scenario
from ops import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer, ServiceStatus

from tests.unit.certificates_helpers import example_cert_and_key
from tests.unit.fixtures import SMFUnitTestFixtures


class TestCharmCollectUnitStatus(SMFUnitTestFixtures):
    def test_given_fiveg_nrf_relation_not_created_when_collect_unit_status_then_status_is_blocked(
        self,
    ):
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[certificates_relation, sdcore_config_relation],
        )

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == BlockedStatus("Waiting for fiveg_nrf relation(s)")

    def test_given_certificates_relation_not_created_when_collect_unit_status_then_status_is_blocked(  # noqa: E501
        self,
    ):
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[nrf_relation, sdcore_config_relation],
        )

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == BlockedStatus("Waiting for certificates relation(s)")

    def test_given_sdcore_config_relation_not_created_when_collect_unit_status_then_status_is_blocked(  # noqa: E501
        self,
    ):
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[nrf_relation, certificates_relation],
        )

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == BlockedStatus("Waiting for sdcore_config relation(s)")

    def test_given_nrf_data_not_available_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[
                certificates_relation,
                sdcore_config_relation,
                nrf_relation,
            ],
        )
        self.mock_nrf_url.return_value = ""

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == WaitingStatus("Waiting for NRF relation to be available")

    def test_given_webui_data_not_available_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[
                nrf_relation,
                certificates_relation,
                sdcore_config_relation,
            ],
        )
        self.mock_sdcore_config_webui_url.return_value = ""
        self.mock_nrf_url.return_value = "http://nrf"

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == WaitingStatus("Waiting for Webui data to be available")

    def test_given_storage_not_attached_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[
                nrf_relation,
                certificates_relation,
                sdcore_config_relation,
            ],
        )
        self.mock_nrf_url.return_value = "http://nrf"

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.unit_status == WaitingStatus("Waiting for storage to be attached")

    def test_given_empty_ip_address_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            certs_mount = scenario.Mount(
                location="/support/TLS",
                src=tempdir,
            )
            config_mount = scenario.Mount(
                location="/etc/smf",
                src=tempdir,
            )
            container = scenario.Container(
                name="smf", can_connect=True, mounts={"certs": certs_mount, "config": config_mount}
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            self.mock_check_output.return_value = b""
            self.mock_nrf_url.return_value = "http://nrf"

            state_out = self.ctx.run("collect_unit_status", state_in)

            assert state_out.unit_status == WaitingStatus(
                "Waiting for pod IP address to be available"
            )

    def test_given_certificates_not_stored_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            config_mount = scenario.Mount(
                location="/etc/smf",
                src=tempdir,
            )
            certs_mount = scenario.Mount(
                location="/support/TLS",
                src=tempdir,
            )
            container = scenario.Container(
                name="smf",
                can_connect=True,
                mounts={
                    "config": config_mount,
                    "certs": certs_mount,
                },
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            self.mock_get_assigned_certificate.return_value = (None, None)
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_nrf_url.return_value = "http://nrf"
            with open(f"{tempdir}/smf.csr", "w") as f:
                f.write("whatever csr")

            state_out = self.ctx.run("collect_unit_status", state_in)

            assert state_out.unit_status == WaitingStatus(
                "Waiting for certificates to be available"
            )

    def test_smf_service_not_running_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            certs_mount = scenario.Mount(
                location="/support/TLS",
                src=tempdir,
            )
            config_mount = scenario.Mount(
                location="/etc/smf",
                src=tempdir,
            )
            container = scenario.Container(
                name="smf",
                layers={"smf": Layer({"services": {}})},
                can_connect=True,
                mounts={"certs": certs_mount, "config": config_mount},
                service_status={"smf": ServiceStatus.INACTIVE},
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            provider_certificate, private_key = example_cert_and_key(
                relation_id=certificates_relation.relation_id
            )
            self.mock_get_assigned_certificate.return_value = (provider_certificate, private_key)
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_nrf_url.return_value = "http://nrf"

            state_out = self.ctx.run("collect_unit_status", state_in)

            assert state_out.unit_status == WaitingStatus("Waiting for SMF service to start")

    def test_relations_available_and_config_pushed_and_pebble_updated_when_collect_unit_status_then_status_is_active(  # noqa: E501
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            certs_mount = scenario.Mount(
                location="/support/TLS",
                src=tempdir,
            )
            config_mount = scenario.Mount(
                location="/etc/smf",
                src=tempdir,
            )
            container = scenario.Container(
                name="smf",
                layers={
                    "smf": Layer(
                        {
                            "services": {
                                "smf": {
                                    "startup": "enabled",
                                    "override": "replace",
                                    "command": "/bin/smf --smfcfg /etc/smf/smfcfg.conf",
                                    "environment": {
                                        "GOTRACEBACK": "crash",
                                        "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                                        "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                                        "GRPC_TRACE": "all",
                                        "GRPC_VERBOSITY": "DEBUG",
                                        "POD_IP": "1.1.1.1",
                                        "MANAGED_BY_CONFIG_POD": "true",
                                    },
                                }
                            }
                        }
                    )
                },
                can_connect=True,
                mounts={"certs": certs_mount, "config": config_mount},
                service_status={"smf": ServiceStatus.ACTIVE},
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            provider_certificate, private_key = example_cert_and_key(
                relation_id=certificates_relation.relation_id
            )
            self.mock_get_assigned_certificate.return_value = (provider_certificate, private_key)
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_nrf_url.return_value = "http://nrf"

            state_out = self.ctx.run("collect_unit_status", state_in)

            assert state_out.unit_status == ActiveStatus()

    def test_given_no_workload_version_file_when_collect_unit_status_then_workload_version_not_set(
        self,
    ):
        nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
        certificates_relation = scenario.Relation(
            endpoint="certificates", interface="tls-certificates"
        )
        sdcore_config_relation = scenario.Relation(
            endpoint="sdcore_config", interface="sdcore_config"
        )
        container = scenario.Container(name="smf", can_connect=True)
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[
                nrf_relation,
                certificates_relation,
                sdcore_config_relation,
            ],
        )

        state_out = self.ctx.run("collect_unit_status", state_in)

        assert state_out.workload_version == ""

    def test_given_workload_version_file_when_collect_unit_status_then_workload_version_set(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            workload_version_mount = scenario.Mount(
                location="/etc",
                src=tempdir,
            )
            expected_version = "1.2.3"
            with open(f"{tempdir}/workload-version", "w") as f:
                f.write(expected_version)
            container = scenario.Container(
                name="smf", can_connect=True, mounts={"workload-version": workload_version_mount}
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )

            state_out = self.ctx.run("collect_unit_status", state_in)

            assert state_out.workload_version == expected_version
