# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""HTTP client for OAuth token exchange."""

from types import TracebackType

import requests
from typing_extensions import Self, Type


class HTTPClient:
    """HTTP client for performing OAuth2 client credentials token exchange."""

    def __init__(self, token_url: str) -> None:
        self._token_url = token_url.rstrip("/")
        self._session = requests.Session()
        self._session.verify = False

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType,
    ) -> None:
        """Exit the context manager and close the session."""
        self._session.close()

    def get_access_token(self, client_id: str, client_secret: str) -> str:
        """Exchange client credentials for an access token.

        Args:
            client_id: The OAuth2 client ID.
            client_secret: The OAuth2 client secret.

        Returns:
            The access token string.
        """
        response = self._session.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
            },
            auth=(client_id, client_secret),
        )
        response.raise_for_status()
        token_data = response.json()
        return token_data["access_token"]
