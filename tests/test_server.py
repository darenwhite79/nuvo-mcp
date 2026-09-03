"""Assembling the server: descriptions and schemas are born from the functions."""

import asyncio

import pytest
from conftest import task
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from nuvo_mcp.server import build_server
from nuvo_mcp.tools import DESCRIPTIONS


def test_every_tool_reaches_the_client_with_a_schema(fake):
    tools = asyncio.run(build_server(fake().api).list_tools())

    assert {tool.name for tool in tools} == set(DESCRIPTIONS)
    # The input schema is born from the type hints: a broken annotation would
    # surface only in someone's editor, whereas here it surfaces at once.
    assert all(tool.input_schema["type"] == "object" for tool in tools)
    assert all(tool.description for tool in tools)


def test_the_text_of_a_refusal_reaches_the_model(fake):
    """The invariant that cost a live run.

    MCP lets through to the model only the text of a `ToolError`; everything
    else is replaced with "Error executing tool …". Which means a plain
    ValueError would make every explanation in this package a message into the
    void, and no `pytest.raises` unit test would ever notice.
    """

    server = build_server(fake(tasks=[task(id=1, title="Still in progress")]).api)

    with pytest.raises(ToolError) as error:
        asyncio.run(server.call_tool("log_task", {"task_id": 1}))

    assert not isinstance(error.value, UnexpectedToolError)
    assert "complete_task" in str(error.value)
