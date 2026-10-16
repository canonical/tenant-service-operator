# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pytest_mock import MockerFixture

from clients import HTTPClient


class TestHTTPClient:
    @pytest.mark.parametrize(
        "no_proxy, expected",
        [
            ("", {"https": "http://proxy:3128"}),
            ("other.example.com", {"https": "http://proxy:3128"}),
            ("example.com", None),
        ],
    )
    def test_get_access_token(
        self, mocker: MockerFixture, no_proxy: str, expected: dict | None
    ) -> None:
        """The request goes through the proxy unless no_proxy names the host, and has a timeout."""
        session = mocker.patch("clients.requests.Session").return_value
        session.post.return_value.json.return_value = {"access_token": "the-token"}

        with HTTPClient(
            token_url="https://login.example.com/oauth2/token",
            https_proxy="http://proxy:3128",
            no_proxy=no_proxy,
        ) as client:
            token = client.get_access_token(client_id="client", client_secret="secret")

        assert token == "the-token"
        session.post.assert_called_once_with(
            "https://login.example.com/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=("client", "secret"),
            proxies=expected,
            timeout=10,
        )
