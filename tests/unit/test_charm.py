# Copyright 2023 Ubuntu
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops import testing

from charm import SMFOperatorCharm


class TestCharm(unittest.TestCase):
    # @patch("lightkube.core.client.GenericSyncClient")
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(SMFOperatorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_when_then(self):
        pass
