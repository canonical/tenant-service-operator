# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import secrets
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Generator

import jubilant
import pytest
import requests
from integration.constants import APP_NAME, DB_APP, KRATOS_APP, TRAEFIK_APP
from integration.utils import get_unit_address, juju_model_factory

from src.constants import INTERNAL_ROUTE_INTEGRATION_NAME, KRATOS_INFO_INTEGRATION_NAME


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control.

    This function adds the following options:
    --keep-models, --no-teardown: Keep the Juju model after the test is finished.
    --model: Specify the Juju model to run the tests on.
    --no-deploy, --no-setup: Skip deployment of the charm.
    """
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection based on deployment and model management.

    This function registers the following markers:
    setup: Skip tests if the charm is already deployed.
    teardown: Skip tests if the no_teardown option is set.
    """
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line("markers", "upgrade: tests that upgrade the charm")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options.

    This function skips tests with specific markers based on the provided command-line options:
    - If no_setup is set, tests marked with "setup" are skipped.
    - If no_teardown is set, tests marked with "teardown" are skipped.
    """
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-tenant-service-{secrets.token_hex(4)}"

    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            log = juju_.debug_log(limit=1000)
            print(log, end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0
        if not keep_model:
            with suppress(jubilant.CLIError):
                args = [
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "600s",
                ]
                juju_.cli(*args, include_model=False)


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the path to the charm-under-test."""
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        subprocess.run(["charmcraft", "pack"], check=True)
        if not (charms := list(Path(".").glob("*.charm"))):
            raise RuntimeError("Charm not found and build failed")
        charm = charms[0].absolute()
    return Path(charm)


@pytest.fixture
def http_client() -> Generator[requests.Session, None, None]:
    with requests.Session() as client:
        client.verify = False
        yield client


def integrate_dependencies(juju: jubilant.Juju) -> None:
    """Integrate the charm with all required dependencies."""
    juju.integrate(f"{TRAEFIK_APP}", f"{APP_NAME}:{INTERNAL_ROUTE_INTEGRATION_NAME}")
    juju.integrate(DB_APP, APP_NAME)
    juju.integrate(DB_APP, KRATOS_APP)
    juju.integrate(KRATOS_APP, f"{APP_NAME}:{KRATOS_INFO_INTEGRATION_NAME}")


@pytest.fixture
def public_address(juju: jubilant.Juju) -> str:
    return get_unit_address(juju, app_name=APP_NAME)
