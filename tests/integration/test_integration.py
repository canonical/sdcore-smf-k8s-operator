#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.fixture(scope="module")
@pytest.mark.abort_on_fail
async def build_and_deploy(ops_test):
    """Build the charm-under-test and deploy it."""
    charm = await ops_test.build_charm(".")
    resources = {
        "smf-image": METADATA["resources"]["smf-image"]["upstream-source"],
    }
    await ops_test.model.deploy(
        charm,
        resources=resources,
        application_name=APP_NAME,
        series="jammy",
    )


@pytest.mark.abort_on_fail
async def test_given_charm_is_built_when_deployed_then_status_is_blocked(
    ops_test,
    build_and_deploy,
):
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="blocked",
        timeout=1000,
    )
