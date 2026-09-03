"""A client for the Nuvo HTTP API.

The server deliberately does not reach into the database: the rules about
scopes, the action log and the validation would otherwise drift apart into two
paths, and the agent would end up with a way around the key.

Errors are translated into human language right here. The agent shows the text
of the exception verbatim, so "ConnectError('[Errno 61] Connection refused')"
would mean the person never learns what to fix.
"""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError


class NuvoError(ToolError):
    """A failure the agent has to be told about in words.

    Inheriting from `ToolError` is not decoration: everything else MCP treats as
    a crashed tool and replaces the text with "Error executing tool …". In other
    words, any other exception would cost us exactly what these messages were
    written for.
    """


class NoRight(NuvoError, PermissionError):
    """The key is missing a scope. A kind of its own: this is fixed by issuing a
    new key rather than by retrying, and the caller benefits from telling it
    apart from other refusals."""


class NuvoApi:
    """A client for our own API. Scopes are checked by the server, not by this wrapper."""

    def __init__(
        self,
        base_url: str,
        token: str,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        # The header is encoded as ASCII. A real key is `nv_` plus random safe
        # characters, but a typo lands in the environment variable too: without
        # this check it would surface as a UnicodeEncodeError deep inside httpx.
        if not token.isascii():
            raise NuvoError(
                "NUVO_TOKEN contains non-ASCII characters. A key looks like "
                "'nv_' followed by Latin letters and digits — something extra got copied in."
            )
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(
                method, path, headers={"Authorization": f"Bearer {self.token}"}, **kwargs
            )
        except httpx.TimeoutException as error:
            raise NuvoError(
                f"Nuvo did not answer in time ({self.base_url}). "
                "The server is probably busy, or the address leads somewhere else."
            ) from error
        except httpx.RequestError as error:
            raise NuvoError(
                f"Nuvo is not answering at {self.base_url}. Check that the app is running "
                "(`make api`) and that NUVO_URL points at it."
            ) from error

        if response.status_code == 401:
            raise NoRight(
                "The key is unknown or has been revoked. Issue a new one on the Connection "
                "screen and put it into NUVO_TOKEN."
            )
        if response.status_code == 403:
            raise NoRight(
                f"The key has no right to this action: {method} {path}. "
                "Rights are granted when the key is created: read, create, edit, delete."
            )
        if response.status_code >= 400:
            raise NuvoError(f"Nuvo refused ({response.status_code}): {detail_of(response)}")
        return response.json() if response.content else None

    def state(self) -> dict[str, Any]:
        """The whole snapshot: areas, projects, headings, tasks, tags, filters."""

        return self.call("GET", "/api/state")

    def reachable(self) -> str | None:
        """A connection check at startup. Returns a complaint, or None if all is well.

        It takes an open route: no key needed, nothing written to the log, and no
        pulling of the whole snapshot. Whether the key itself is any good comes
        out on the very first tool call — and says so plainly.
        """

        try:
            response = self._client.get("/api/health", timeout=5.0)
        except httpx.RequestError:
            return (
                f"Nuvo is not answering at {self.base_url}. The tools will keep returning "
                "errors until the app comes up. Start it with: make api"
            )
        if response.status_code != 200:
            return (
                f"Something is answering at {self.base_url}, but it is not Nuvo: "
                f"/api/health returned {response.status_code}."
            )
        return None


def detail_of(response: httpx.Response) -> str:
    """The explanation from the response body. FastAPI puts it in `detail`."""

    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or "the server said nothing"
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]
