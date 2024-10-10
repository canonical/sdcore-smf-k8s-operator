# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import tempfile

from ops import testing

from tests.unit.fixtures import SMFUnitTestFixtures


class TestCharmCertificatesRelationBroken(SMFUnitTestFixtures):
    def test_given_certificates_are_stored_when_on_certificates_relation_broken_then_certificates_are_removed(  # noqa: E501
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            certificates_relation = testing.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            certs_mount = testing.Mount(
                location="/support/TLS",
                source=tempdir,
            )
            config_mount = testing.Mount(
                location="/etc/smf",
                source=tempdir,
            )
            container = testing.Container(
                name="smf",
                can_connect=True,
                mounts={"certs": certs_mount, "config": config_mount},
            )
            os.mkdir(f"{tempdir}/support")
            os.mkdir(f"{tempdir}/support/TLS")
            with open(f"{tempdir}/smf.pem", "w") as f:
                f.write("certificate")

            with open(f"{tempdir}/smf.key", "w") as f:
                f.write("private key")

            state_in = testing.State(
                relations=[certificates_relation],
                containers=[container],
                leader=True,
            )

            self.ctx.run(self.ctx.on.relation_broken(certificates_relation), state_in)

            assert not os.path.exists(f"{tempdir}/smf.pem")
            assert not os.path.exists(f"{tempdir}/smf.key")
