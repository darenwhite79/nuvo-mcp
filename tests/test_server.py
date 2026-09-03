"""Сборка сервера: описания и схемы рождаются из самих функций."""

import asyncio

import pytest
from conftest import task
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from nuvo_mcp.server import build_server
from nuvo_mcp.tools import DESCRIPTIONS


def test_все_инструменты_доезжают_до_клиента_со_схемой(fake):
    tools = asyncio.run(build_server(fake().api).list_tools())

    assert {tool.name for tool in tools} == set(DESCRIPTIONS)
    # Схема входа рождается из подсказок типов: сломанная аннотация всплыла бы
    # только у человека в редакторе, а тут — сразу.
    assert all(tool.input_schema["type"] == "object" for tool in tools)
    assert all(tool.description for tool in tools)


def test_текст_отказа_доходит_до_модели(fake):
    """Инвариант, который стоил живого прогона.

    MCP пропускает к модели только текст `ToolError`; всё прочее заменяется на
    «Error executing tool …». То есть обычный ValueError означал бы, что все
    объяснения в этом пакете написаны в пустоту, и ни один юнит-тест на
    `pytest.raises` этого бы не заметил.
    """

    server = build_server(fake(tasks=[task(id=1, title="Ещё в работе")]).api)

    with pytest.raises(ToolError) as error:
        asyncio.run(server.call_tool("log_task", {"task_id": 1}))

    assert not isinstance(error.value, UnexpectedToolError)
    assert "complete_task" in str(error.value)
