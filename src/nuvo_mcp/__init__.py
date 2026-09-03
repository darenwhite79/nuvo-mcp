"""An MCP server for Nuvo tasks.

The package stands on its own: `mcp` and `httpx` are the only dependencies, and
it reaches the backend over HTTP rather than by import. That is why it installs
and runs in a single line — `uvx nuvo-mcp` — wherever the app itself lives.
"""

from nuvo_mcp.api import NoRight, NuvoApi, NuvoError
from nuvo_mcp.server import build_server, main
from nuvo_mcp.tools import DESCRIPTIONS, day_view, make_tools, tasks_of

__all__ = [
    "DESCRIPTIONS",
    "NoRight",
    "NuvoApi",
    "NuvoError",
    "build_server",
    "day_view",
    "main",
    "make_tools",
    "tasks_of",
]
