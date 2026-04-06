# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import uuid
from pathlib import Path
from typing import Iterator

import jubilant
import pytest
import requests
from integration.utils import create_temp_juju_model


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control."""
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        action="store_true",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection."""
    config.addinivalue_line("markers", "skip_if_deployed: skip test if deployed")
    config.addinivalue_line("markers", "skip_if_keep_models: skip test if --keep-models is set.")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options."""
    for item in items:
        if config.getoption("--no-deploy") and "skip_if_deployed" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="skipping deployment"))
        if config.getoption("--keep-models") and "skip_if_keep_models" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="skipping test because --keep-models is set"))


@pytest.fixture(scope="module")
def model(request: pytest.FixtureRequest) -> Iterator[jubilant.Juju]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-tenant-service-{uuid.uuid4().hex[-8:]}"

    yield from create_temp_juju_model(request, model=model_name)


@pytest.fixture(scope="module")
def local_charm(model: jubilant.Juju) -> Path:
    """Get the path to the charm-under-test."""
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        import subprocess

        subprocess.run(["charmcraft", "pack"], check=True)
        charms = list(Path(".").glob("*.charm"))
        if charms:
            charm = charms[0].absolute()
        else:
            raise RuntimeError("Charm not found and build failed")
    return Path(charm)


@pytest.fixture(scope="module")
def charm_config() -> dict:
    """Configuration for the charm."""
    return {}


@pytest.fixture
def http_client() -> requests.Session:
    """Create an HTTP session that ignores TLS verification."""
    session = requests.Session()
    session.verify = False
    return session
