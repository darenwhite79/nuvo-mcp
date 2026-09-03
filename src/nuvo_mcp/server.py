"""Assembling and running the MCP server.

The transport is stdio: the channel belongs to the protocol entirely, so
everything written for a human goes to stderr. A line on stdout would break the
conversation with the client.

Run it with:
    NUVO_TOKEN=nv_… uvx nuvo-mcp
"""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer

from nuvo_mcp.api import NuvoApi, NuvoError
from nuvo_mcp.tools import DESCRIPTIONS, make_tools

DEFAULT_URL = "http://127.0.0.1:8000"

#: The model reads this when deciding whether to call this server at all.
INSTRUCTIONS = """\
Nuvo is a task manager: area → project → task, plus checklists and tags.

How things are done here:
- "Today" is a commitment to do it today, not a priority flag. Give it only to
  what the person is taking on today.
- The deadline and the day of doing are different things: a deadline says
  "after this it is too late", the day says "I'll get to it then".
- There are no separate comments: their place is the task's notes, where
  add_note appends a dated paragraph without erasing anything.
- Before creating a task, look for a similar one with search_tasks: a duplicate
  is worse than nothing.
- The agent has no permanent delete, on purpose. Emptying the trash is the
  person's own job.

The server talks to the same HTTP API as the app, so it obeys the scopes of the
key, and everything it does is visible in that key's log.
"""

NO_TOKEN = """\
NUVO_TOKEN is not set — without an access key Nuvo will not let you in.

Where to get one: open the app → Settings → Connection, and issue a key with the
Read, Create and Edit scopes. The token is shown once.

Without the interface the API issues keys itself, locally and without a key:
    curl -X POST http://127.0.0.1:8000/api/keys \\
      -H 'Content-Type: application/json' \\
      -d '{"title":"My agent","scopes":"read,create,edit"}'

Then put it into the configuration of your client:
    "env": { "NUVO_TOKEN": "nv_…", "NUVO_URL": "http://127.0.0.1:8000" }
"""


def build_server(api: NuvoApi) -> MCPServer:
    server = MCPServer(name="nuvo", version="0.1.0", instructions=INSTRUCTIONS)
    for name, function in make_tools(api).items():
        server.tool(name=name, description=DESCRIPTIONS[name])(function)
    return server


def main() -> None:
    token = os.environ.get("NUVO_TOKEN", "").strip()
    if not token:
        raise SystemExit(NO_TOKEN)

    try:
        api = NuvoApi(os.environ.get("NUVO_URL", "").strip() or DEFAULT_URL, token)
    except NuvoError as error:
        # The configuration was read wrong — that is a conversation with a
        # person, not a program failure: a traceback here only gets in the way
        # of reading what to fix.
        raise SystemExit(str(error)) from None

    # Complain, but do not die: the client starts the server together with the
    # editor, while the app is brought up whenever it happens. Dying here would
    # mean demanding that the editor be restarted for the sake of start order.
    complaint = api.reachable()
    if complaint:
        print(complaint, file=sys.stderr, flush=True)

    build_server(api).run(transport="stdio")


if __name__ == "__main__":
    main()
