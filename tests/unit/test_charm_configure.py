# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime
import os
import tempfile

import scenario
from charms.tls_certificates_interface.v3.tls_certificates import ProviderCertificate
from ops.pebble import Layer

from tests.unit.fixtures import SMFUnitTestFixtures


class TestCharmConfigure(SMFUnitTestFixtures):
    def test_given_relations_created_and_database_available_and_nrf_data_available_and_certs_stored_when_pebble_ready_then_config_file_rendered_and_pushed_correctly(  # noqa: E501
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            database_relation = scenario.Relation(endpoint="database", interface="mongodb_client")
            self.mock_db_fetch_relation_data.return_value = {
                database_relation.relation_id: {"uris": "http://6.5.6.5"}
            }
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
                    database_relation,
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
                model=scenario.Model(name="whatever"),
            )
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_generate_private_key.return_value = b"whatever private key"
            self.mock_generate_csr.return_value = b"whatever csr"
            provider_certificate = ProviderCertificate(
                relation_id=certificates_relation.relation_id,
                application_name="pcf",
                csr="whatever csr",
                certificate="whatever cert",
                ca="whatever ca",
                chain=["whatever ca", "whatever cert"],
                revoked=False,
                expiry_time=datetime.datetime.now(),
            )
            self.mock_get_assigned_certificates.return_value = [provider_certificate]
            self.mock_db_is_resource_created.return_value = True
            self.mock_nrf_url.return_value = "https://nrf:443"
            self.mock_sdcore_config_webui_url.return_value = "sdcore-webui:9876"

            self.ctx.run(container.pebble_ready_event, state_in)

            with open(tempdir + "/smf.pem", "r") as f:
                assert f.read() == str(provider_certificate.certificate)

            with open(tempdir + "/smfcfg.yaml", "r") as f:
                actual_config = f.read().strip()

            with open("tests/unit/expected_smfcfg.yaml", "r") as f:
                expected_config = f.read().strip()

            assert actual_config == expected_config

    def test_given_content_of_config_file_not_changed_when_pebble_ready_then_config_file_is_not_pushed(  # noqa: E501
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            database_relation = scenario.Relation(endpoint="database", interface="mongodb_client")
            self.mock_db_fetch_relation_data.return_value = {
                database_relation.relation_id: {"uris": "http://6.5.6.5"}
            }
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
                    database_relation,
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
                model=scenario.Model(name="whatever"),
            )
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_generate_private_key.return_value = b"whatever private key"
            self.mock_generate_csr.return_value = b"whatever csr"
            provider_certificate = ProviderCertificate(
                relation_id=certificates_relation.relation_id,
                application_name="pcf",
                csr="whatever csr",
                certificate="whatever cert",
                ca="whatever ca",
                chain=["whatever ca", "whatever cert"],
                revoked=False,
                expiry_time=datetime.datetime.now(),
            )
            self.mock_get_assigned_certificates.return_value = [provider_certificate]
            self.mock_db_is_resource_created.return_value = True
            self.mock_nrf_url.return_value = "https://nrf:443"
            self.mock_sdcore_config_webui_url.return_value = "sdcore-webui:9876"
            with open(tempdir + "smf.csrs", "w") as f:
                f.write("whatever csr")
            with open(tempdir + "/smf.pem", "w") as f:
                f.write(str(provider_certificate.certificate))
            with open(tempdir + "/smf.key", "w") as f:
                f.write("whatever private key")
            with open("tests/unit/expected_smfcfg.yaml", "r") as f:
                expected_config = f.read()
            with open(tempdir + "/smfcfg.yaml", "w") as f:
                f.write(expected_config)
            config_modification_time = os.stat(tempdir + "/smfcfg.yaml").st_mtime

            self.ctx.run(container.pebble_ready_event, state_in)

            assert os.stat(tempdir + "/smfcfg.yaml").st_mtime == config_modification_time

    def test_given_relations_available_and_config_pushed_when_pebble_ready_then_pebble_is_applied_correctly(  # noqa: E501
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            database_relation = scenario.Relation(endpoint="database", interface="mongodb_client")
            self.mock_db_fetch_relation_data.return_value = {
                database_relation.relation_id: {"uris": "http://dummy"}
            }
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
                    database_relation,
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            self.mock_generate_private_key.return_value = b"whatever private key"
            self.mock_generate_csr.return_value = b"whatever csr"
            provider_certificate = ProviderCertificate(
                relation_id=certificates_relation.relation_id,
                application_name="pcf",
                csr="whatever csr",
                certificate="whatever cert",
                ca="whatever ca",
                chain=["whatever ca", "whatever cert"],
                revoked=False,
                expiry_time=datetime.datetime.now(),
            )
            self.mock_get_assigned_certificates.return_value = [provider_certificate]
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_db_is_resource_created.return_value = True
            self.mock_nrf_url.return_value = "https://nrf:443"

            state_out = self.ctx.run(container.pebble_ready_event, state_in)

            assert state_out.containers[0].layers == {
                "smf": Layer(
                    {
                        "services": {
                            "smf": {
                                "startup": "enabled",
                                "override": "replace",
                                "command": "/bin/smf -smfcfg /etc/smf/smfcfg.yaml -uerouting /etc/smf/uerouting.yaml",  # noqa: E501
                                "environment": {
                                    "GRPC_GO_LOG_VERBOSITY_LEVEL": "99",
                                    "GRPC_GO_LOG_SEVERITY_LEVEL": "info",
                                    "GRPC_TRACE": "all",
                                    "GRPC_VERBOSITY": "debug",
                                    "PFCP_PORT_UPF": "8805",
                                    "MANAGED_BY_CONFIG_POD": "true",
                                    "POD_IP": "1.1.1.1",
                                },
                            }
                        }
                    }
                )
            }

    def test_given_can_connect_when_on_pebble_ready_then_private_key_is_generated(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            database_relation = scenario.Relation(endpoint="database", interface="mongodb_client")
            self.mock_db_fetch_relation_data.return_value = {
                database_relation.relation_id: {"uris": "http://dummy"}
            }
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
                    database_relation,
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
            )
            self.mock_generate_private_key.return_value = b"whatever private key"
            self.mock_generate_csr.return_value = b"whatever csr"
            provider_certificate = ProviderCertificate(
                relation_id=certificates_relation.relation_id,
                application_name="pcf",
                csr="whatever csr",
                certificate="whatever cert",
                ca="whatever ca",
                chain=["whatever ca", "whatever cert"],
                revoked=False,
                expiry_time=datetime.datetime.now(),
            )
            self.mock_get_assigned_certificates.return_value = [provider_certificate]
            self.mock_check_output.return_value = b"1.1.1.1"

            self.ctx.run(container.pebble_ready_event, state_in)

            with open(tempdir + "/smf.key", "r") as f:
                assert f.read() == "whatever private key"

    def test_given_certificate_matches_stored_one_when_pebble_ready_then_certificate_is_not_pushed(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            database_relation = scenario.Relation(endpoint="database", interface="mongodb_client")
            self.mock_db_fetch_relation_data.return_value = {
                database_relation.relation_id: {"uris": "http://dummy"}
            }
            nrf_relation = scenario.Relation(endpoint="fiveg_nrf", interface="fiveg_nrf")
            certificates_relation = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            sdcore_config_relation = scenario.Relation(
                endpoint="sdcore_config", interface="sdcore_config"
            )
            container = scenario.Container(
                name="smf",
                can_connect=True,
                mounts={
                    "certs": scenario.Mount(
                        location="/support/TLS",
                        src=tempdir,
                    ),
                    "config": scenario.Mount(
                        location="/etc/smf",
                        src=tempdir,
                    ),
                },
            )
            state_in = scenario.State(
                leader=True,
                relations=[
                    database_relation,
                    nrf_relation,
                    certificates_relation,
                    sdcore_config_relation,
                ],
                containers=[container],
            )
            self.mock_check_output.return_value = b"1.1.1.1"
            self.mock_nrf_url.return_value = "https://nrf:443"
            self.mock_generate_private_key.return_value = b"whatever private key"
            self.mock_generate_csr.return_value = b"whatever csr"
            provider_certificate = ProviderCertificate(
                relation_id=certificates_relation.relation_id,
                application_name="pcf",
                csr="whatever csr",
                certificate="whatever cert",
                ca="whatever ca",
                chain=["whatever ca", "whatever cert"],
                revoked=False,
                expiry_time=datetime.datetime.now(),
            )
            with open(f"{tempdir}/smf.pem", "w") as f:
                f.write(str(provider_certificate.certificate))
            with open(f"{tempdir}/smf.key", "w") as f:
                f.write("whatever private key")
            self.mock_get_assigned_certificates.return_value = [provider_certificate]
            config_modification_time_smf_pem = os.stat(tempdir + "/smf.pem").st_mtime
            config_modification_time_smf_key = os.stat(tempdir + "/smf.key").st_mtime

            self.ctx.run(container.pebble_ready_event, state_in)

            assert os.stat(tempdir + "/smf.pem").st_mtime == config_modification_time_smf_pem
            assert os.stat(tempdir + "/smf.key").st_mtime == config_modification_time_smf_key
