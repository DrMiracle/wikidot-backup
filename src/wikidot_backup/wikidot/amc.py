"""Low-level client for Wikidot's AJAX Module Connector (AMC)."""

from __future__ import annotations

import secrets
from typing import Any

import httpx


class WikidotAmcClient:
    """Send low-level requests to Wikidot's AJAX Module Connector."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        """Initialize an AMC client for a Wikidot site."""

        self.base_url = base_url.rstrip("/")

        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
        )

    def request(
        self,
        module_name: str,
        *,
        path_suffix: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """Execute a Wikidot AJAX module request.

        Args:
            module_name:
                Wikidot module name, for example ``list/ListPagesModule``.

            path_suffix:
                Optional Wikidot URL-state suffix such as ``/p/2``.
                Some modules use URL path parameters rather than POST
                parameters for pagination.

            **params:
                Parameters passed to the requested Wikidot module.

        Returns:
            Decoded Wikidot JSON response.

        Raises:
            httpx.HTTPError:
                If the HTTP request fails.

            RuntimeError:
                If Wikidot returns a non-OK module response.
        """

        token = secrets.token_hex(8)

        data = {
            "moduleName": module_name,
            "wikidot_token7": token,
            **params,
        }

        response = self._http.post(
            (
                f"{self.base_url}"
                f"/ajax-module-connector.php"
                f"{path_suffix}"
            ),
            data=data,
            cookies={
                "wikidot_token7": token,
            },
        )

        response.raise_for_status()

        result = response.json()

        if result.get("status") != "ok":
            raise RuntimeError(
                f"Wikidot AMC error: {result}"
            )

        return result

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._http.close()
