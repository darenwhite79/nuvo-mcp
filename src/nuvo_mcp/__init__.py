"""MCP-сервер к делам Nuvo.

Пакет самодостаточен: из зависимостей только `mcp` и `httpx`, к бэкенду он
ходит по HTTP, а не импортом. Поэтому ставится и запускается одной строкой —
`uvx nuvo-mcp` — где бы ни лежало само приложение.
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
