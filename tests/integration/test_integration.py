#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from collections import Counter
from pathlib import Path

import pytest
import yaml
from juju.application import Application
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
NRF_APP_NAME = "sdcore-nrf-k8s"
DATABASE_APP_NAME = "mongodb-k8s"
TLS_PROVIDER_APP_NAME = "self-signed-certificates"
GRAFANA_AGENT_APP_NAME = "grafana-agent-k8s"


async def _deploy_database(ops_test: OpsTest):
    """Deploy a MongoDB."""
    assert ops_test.model
    await ops_test.model.deploy(
        DATABASE_APP_NAME,
        application_name=DATABASE_APP_NAME,
        channel="6/beta",
        trust=True,
    )


async def _deploy_nrf(ops_test: OpsTest):
    """Deploy a NRF."""
    assert ops_test.model
    await ops_test.model.deploy(
        NRF_APP_NAME,
        application_name=NRF_APP_NAME,
        channel="edge",
        trust=True,
    )


async def _deploy_tls_provider(ops_test: OpsTest):
    """Deploy a TLS provider."""
    assert ops_test.model
    await ops_test.model.deploy(
        TLS_PROVIDER_APP_NAME,
        application_name=TLS_PROVIDER_APP_NAME,
        channel="beta",
    )


async def _deploy_grafana_agent(ops_test: OpsTest):
    """Deploy a Grafana agent."""
    assert ops_test.model
    await ops_test.model.deploy(
        GRAFANA_AGENT_APP_NAME,
        application_name=GRAFANA_AGENT_APP_NAME,
        channel="stable",
    )


@pytest.fixture(scope="module")
@pytest.mark.abort_on_fail
async def build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it."""
    assert ops_test.model
    charm = await ops_test.build_charm(".")
    resources = {
        "smf-image": METADATA["resources"]["smf-image"]["upstream-source"],
    }
    await ops_test.model.deploy(
        charm,
        resources=resources,
        application_name=APP_NAME,
        trust=True,
    )
    await _deploy_database(ops_test)
    await _deploy_nrf(ops_test)
    await _deploy_tls_provider(ops_test)
    await _deploy_grafana_agent(ops_test)


@pytest.mark.abort_on_fail
async def test_given_charm_is_built_when_deployed_then_status_is_blocked(
    ops_test: OpsTest, build_and_deploy
):
    assert ops_test.model
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="blocked",
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_relate_and_wait_for_active_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.integrate(
        relation1=f"{NRF_APP_NAME}:database", relation2=f"{DATABASE_APP_NAME}"
    )
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:database", relation2=f"{DATABASE_APP_NAME}"
    )
    await ops_test.model.integrate(relation1=NRF_APP_NAME, relation2=TLS_PROVIDER_APP_NAME)
    await ops_test.model.integrate(relation1=APP_NAME, relation2=NRF_APP_NAME)
    await ops_test.model.integrate(relation1=APP_NAME, relation2=TLS_PROVIDER_APP_NAME)
    await ops_test.model.integrate(
        relation1=f"{APP_NAME}:logging", relation2=GRAFANA_AGENT_APP_NAME
    )
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_remove_nrf_and_wait_for_blocked_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.remove_application(NRF_APP_NAME, block_until_done=True)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", timeout=60)


@pytest.mark.abort_on_fail
async def test_restore_nrf_and_wait_for_active_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.deploy(
        NRF_APP_NAME,
        application_name=NRF_APP_NAME,
        channel="edge",
        trust=True,
    )
    await ops_test.model.integrate(
        relation1=f"{NRF_APP_NAME}:database", relation2=DATABASE_APP_NAME
    )
    await ops_test.model.integrate(relation1=NRF_APP_NAME, relation2=TLS_PROVIDER_APP_NAME)
    await ops_test.model.integrate(relation1=APP_NAME, relation2=NRF_APP_NAME)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)


@pytest.mark.abort_on_fail
async def test_remove_tls_and_wait_for_blocked_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.remove_application(TLS_PROVIDER_APP_NAME, block_until_done=True)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", timeout=60)


@pytest.mark.abort_on_fail
async def test_restore_tls_and_wait_for_active_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.deploy(
        TLS_PROVIDER_APP_NAME,
        application_name=TLS_PROVIDER_APP_NAME,
        channel="beta",
        trust=True,
    )
    await ops_test.model.integrate(relation1=APP_NAME, relation2=TLS_PROVIDER_APP_NAME)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)


@pytest.mark.abort_on_fail
async def test_when_scale_app_beyond_1_then_only_one_unit_is_active(
    ops_test: OpsTest, build_and_deploy
):
    assert ops_test.model
    assert isinstance(app := ops_test.model.applications[APP_NAME], Application)
    await app.scale(3)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], timeout=1000, wait_for_at_least_units=3)
    unit_statuses = Counter(unit.workload_status for unit in app.units)
    assert unit_statuses.get("active") == 1
    assert unit_statuses.get("blocked") == 2


async def test_remove_app(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.remove_application(APP_NAME, block_until_done=True)


@pytest.mark.skip(
    reason="Bug in MongoDB: https://github.com/canonical/mongodb-k8s-operator/issues/218"
)
@pytest.mark.abort_on_fail
async def test_remove_database_and_wait_for_blocked_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.remove_application(DATABASE_APP_NAME, block_until_done=True)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", timeout=60)


@pytest.mark.skip(
    reason="Bug in MongoDB: https://github.com/canonical/mongodb-k8s-operator/issues/218"
)
@pytest.mark.abort_on_fail
async def test_restore_database_and_wait_for_active_status(ops_test: OpsTest, build_and_deploy):
    assert ops_test.model
    await ops_test.model.deploy(
        DATABASE_APP_NAME,
        application_name=DATABASE_APP_NAME,
        channel="5/edge",
        trust=True,
    )
    await ops_test.model.integrate(relation1=APP_NAME, relation2=DATABASE_APP_NAME)
    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", timeout=1000)
