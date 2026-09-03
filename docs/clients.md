# Connecting an assistant to Nuvo (MCP)

MCP is a way to give an assistant program the same rights over your tasks that
you have. The assistant does not reach into the database; it uses the same HTTP
API as the app, so everything it does shows up in the app immediately and is
written to the key's log.

Ready-made system prompts that make an assistant handle tasks sensibly live in
[prompts.md](prompts.md).

## In short

1. Start the app: `make api` (address `http://127.0.0.1:8000`).
2. Issue a key: Settings → Connection → Issue key. The token is shown once.
3. Paste the configuration snippet for your client (below) and restart it.
4. Ask the assistant "what do I have today?" — it should answer with a list.

## Step 1. Where to get a key

**In the app.** Foot of the sidebar → Settings → Connection. Tick the rights and
press Issue key:

| Right      | What it opens                             |
|------------|-------------------------------------------|
| `read`     | Lists and tasks                           |
| `create`   | New tasks, projects, areas, tags           |
| `edit`     | Editing, including completing              |
| `delete`   | Permanent deletion from the trash          |

`read,create,edit` is usually enough for an assistant. It never uses `delete`:
it has no permanent-deletion tool, on purpose.

The same screen has a ready-made configuration block, with your key and path
already filled in. Copy it with the button and move on to step 2.

**Self-hosted is free; the Telegram version costs stars.** Access from outside
(API keys, MCP, webhooks) is a paid capability in Telegram: until it is paid
for, issuing a key answers `402` and explains in words what is missing. On a
self-hosted install — the one you brought up yourself, which nobody signs into
through Telegram — there is nothing to pay for: keys are issued as before. The
MCP server itself has nothing to do with payment, but it depends on it: what is
paid for is outside access as such, not a one-off key issue. When the paid
period runs out, a request made with the key answers `402`, and the reminder
mailout stops counting those tasks. The tasks themselves stay put and go
nowhere: the app works as it worked, only the door to the outside closes. Pay
again and the same key works without being reissued.

Only three things are paid for: push reminders, the day calendar with ICS
import, and access from outside (keys, MCP, webhooks). Tasks, projects, areas,
lists, checklists, tags, notes, repeats and search are free and unlimited in
number, and **export is free forever**: you can take your tasks with you even
after the payment has run out.

**Without the interface.** Locally, keys are issued without a key:

```bash
curl -X POST http://127.0.0.1:8000/api/keys \
  -H 'Content-Type: application/json' \
  -d '{"title":"My assistant","scopes":"read,create,edit"}'
```

A key opens the whole database, so treat it like a password. It is revoked
where it was issued; the log of a revoked key stays.

## Step 2. What starts the server

One line, with no cloning of the repository:

```bash
NUVO_TOKEN=nv_… uvx nuvo-mcp
```

> The `nuvo-mcp` package is not on PyPI yet. Until it is, write installation
> straight from the repository everywhere `uvx nuvo-mcp` appears below — there
> is still nothing to clone:
>
> ```bash
> NUVO_TOKEN=nv_… uvx --from git+https://github.com/darenwhite79/nuvo-mcp.git nuvo-mcp
> ```
>
> That is, `"command": "uvx"` and, in `args`,
> `["--from", "git+https://github.com/darenwhite79/nuvo-mcp.git", "nuvo-mcp"]`.
> A ready block with the key filled in is on the Connection screen in the app.

You need [uv](https://docs.astral.sh/uv/) (`brew install uv` or
`curl -LsSf https://astral.sh/uv/install.sh | sh`). `uvx` installs the package
into a temporary environment by itself — there is no Python to set up.

| Variable     | Required | Default                 | What it is                        |
|--------------|----------|-------------------------|-----------------------------------|
| `NUVO_TOKEN` | yes      | —                       | The access key from step 1         |
| `NUVO_URL`   | no       | `http://127.0.0.1:8000` | The address the app is running at  |

Started without `NUVO_TOKEN`, it prints where to get a key. Started while the
app is down, it prints that the app is not answering but stays alive: the order
in which the editor and the app start does not matter.

## Step 3. Configuring the client

### Claude Code

The command is the shortest path. `--` separates Claude's own flags from the
command that starts the server, and `-s user` makes the server shared across all
projects (`local` — only the current one, `project` — in the repository's
`.mcp.json`):

```bash
claude mcp add nuvo -s user \
  -e NUVO_TOKEN=nv_… \
  -e NUVO_URL=http://127.0.0.1:8000 \
  -- uvx nuvo-mcp
```

The same thing as one piece of JSON:

```bash
claude mcp add-json -s user nuvo \
  '{"type":"stdio","command":"uvx","args":["nuvo-mcp"],"env":{"NUVO_TOKEN":"nv_…","NUVO_URL":"http://127.0.0.1:8000"}}'
```

As a file — `~/.claude.json` (for `user`) or `.mcp.json` in the project root
(for `project`):

```json
{
  "mcpServers": {
    "nuvo": {
      "type": "stdio",
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "nv_…",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

In `.mcp.json` the key need not be written in the clear: `${NUVO_TOKEN}` and
`${NUVO_URL:-http://127.0.0.1:8000}` are expanded from the environment there.

To check: `claude mcp list` shows `nuvo` and the state of the connection; `/mcp`
does the same inside a conversation.

Source: [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp).

### Claude Desktop

Settings → Developer → Edit Config. The file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: **not confirmed.** The Linux app exists in beta, but the official
  documentation does not name the config path; the widely quoted
  `~/.config/Claude/claude_desktop_config.json` shows up only in third-party
  guides. It is safer to open the file through the Developer → Edit Config menu
  itself.

```json
{
  "mcpServers": {
    "nuvo": {
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "nv_…",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

After editing, the app has to be quit completely and opened again. Write paths
in `args` as absolute ones: the app has a working directory of its own. To
check, see step 4.

Source:
[modelcontextprotocol.io/docs/develop/connect-local-servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

### Cursor

`~/.cursor/mcp.json` (for every project) or `.cursor/mcp.json` (for one). Cursor
works out the transport from the fields: a local server is given by `command`
(with `args` and `env`), a remote one by `url`. There is no separate `type`
field in the examples in the official documentation, and stdio does not need
one:

```json
{
  "mcpServers": {
    "nuvo": {
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "nv_…",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

**An install link.** Cursor understands a deeplink of the form

```
cursor://anysphere.cursor-deeplink/mcp/install?name=nuvo&config=<base64 of the JSON>
```

where `config` is a JSON string encoded in base64. Build your own like this:

```bash
python3 -c '
import base64, json, sys
config = {"command": "uvx", "args": ["nuvo-mcp"],
          "env": {"NUVO_TOKEN": sys.argv[1], "NUVO_URL": "http://127.0.0.1:8000"}}
packed = base64.b64encode(json.dumps(config).encode()).decode()
print(f"cursor://anysphere.cursor-deeplink/mcp/install?name=nuvo&config={packed}")
' nv_your_key
```

The body of `config` is the **bare** configuration object of a single server
(`{"command": …, "args": […], "env": {…}}`), with no name wrapped around it:
Cursor takes the server name from the separate, required `name` parameter. The
script above encodes exactly that. Checked against the official example: the
deeplink in Cursor's documentation is
`cursor://…/mcp/install?name=postgres&config=<base64>`, and the decoded `config`
inside it is `{"command":"npx","args":[…]}` — with no `postgres` key. Right next
to it on the same page, the configuration of a single server is shown in its
`mcp.json` form, wrapped in its name (`{"postgres": {…}}`) — that is the
wrapping of the file, not of the link body, and the two are easy to confuse. And
remember that the key ends up inside the link: it should not be forwarded
anywhere.

Sources: [cursor.com/docs/context/mcp](https://cursor.com/docs/context/mcp),
[cursor.com/docs/mcp/install-links](https://cursor.com/docs/mcp/install-links).

### VS Code + GitHub Copilot

The top-level key here is `servers`, not `mcpServers`. It is better not to write
the access key into the file but to ask for it on first run — that is what
`inputs` is for:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "nuvo-token",
      "description": "Nuvo access key",
      "password": true
    }
  ],
  "servers": {
    "nuvo": {
      "type": "stdio",
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "${input:nuvo-token}",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

The file goes into `.vscode/mcp.json` (for a project) or into the user profile.
The documentation warns separately: the Agent Host reads not
`.vscode/mcp.json` but `.mcp.json` in the root of the working folder, or
`~/.copilot/mcp-config.json`.

By command:

```bash
code --add-mcp "{\"name\":\"nuvo\",\"command\":\"uvx\",\"args\":[\"nuvo-mcp\"]}"
```

**Not verified:** passing `env` inside `--add-mcp`. The documented example has
only `name`, `command` and `args`, and the schema of the flag is not published —
the key is safer added through the file.

The tools show up in the Copilot chat in Agent mode. To check, see step 4.

Sources:
[VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration),
[VS Code: use MCP servers](https://code.visualstudio.com/docs/copilot/customization/mcp-servers).

### Windsurf

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "nuvo": {
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "nv_…",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Source: [docs.windsurf.com/windsurf/cascade/mcp](https://docs.windsurf.com/windsurf/cascade/mcp).

### Zed

Here MCP servers are called context servers, and the key in `settings.json` is
`context_servers`. The file is opened by the `zed::OpenSettingsFile` action; so
does Settings → AI → MCP Servers → Add Server → Add Local Server.

```json
{
  "context_servers": {
    "nuvo": {
      "command": "uvx",
      "args": ["nuvo-mcp"],
      "env": {
        "NUVO_TOKEN": "nv_…",
        "NUVO_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Source: [zed.dev/docs/ai/mcp](https://zed.dev/docs/ai/mcp).

### Claude.ai in the browser

**This cannot be connected, and the settings are not the reason.** The web only
supports remote MCP servers: the connection is made not by the browser but by
Anthropic's infrastructure, so the server has to be reachable from the internet
at a public address. `uvx nuvo-mcp` on your laptop cannot fit that in principle —
nor can any server behind a VPN or a firewall. Local servers from
`claude_desktop_config.json` are a separate mechanism, and it does not work in
the web.

For Nuvo tasks to be visible in the web, a separate public MCP HTTP endpoint is
needed, and Nuvo does not have one yet. Once it does, connecting will live under
Customize → Connectors (for teams, Organization settings → Connectors), on the
Free, Pro, Max, Team and Enterprise plans; Free allows one custom connector.

For now the plain API is what remains for the web: a key and `curl` work from
anywhere, as long as the app is exposed to the outside.

Source:
[support.claude.com — custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp).

## Step 4. Check that it works

Ask the assistant: **"what do I have today?"** It should call `today` and answer
with a list. Then try "add a task 'buy tickets' for tomorrow".

If there is no answer, go through this in order:

| What you see                                   | What to fix                                                                |
|------------------------------------------------|----------------------------------------------------------------------------|
| "NUVO_TOKEN is not set"                        | The key never reached the server: check `env` in the client configuration.  |
| "Nuvo is not answering at …"                   | The app is down — `make api`; or `NUVO_URL` points elsewhere.               |
| "The key is unknown or has been revoked"       | The key was revoked, or copied incompletely. Issue a new one.               |
| `402` when issuing a key or when using it       | The Telegram version: outside access is paid for in stars, and the payment ran out. Tasks are untouched, and self-hosted installs are unaffected. |
| "The key has no right to this action"          | Not enough rights. A key with new rights is issued afresh; the old one stays as it is. |
| The server is missing from the client's list   | The client was not restarted, or `uvx` is not on `PATH` — check `which uvx`. |

By hand, the same way the client does it:

```bash
NUVO_TOKEN=nv_… uvx nuvo-mcp
```

A live server stays quiet and waits: it speaks over stdin/stdout and writes its
complaints to stderr. Ctrl+C to quit.

What the assistant has done is visible in the app: Settings → Connection → the
key's Log. Refusals land there too — you can see where it tried to reach without
the right.

## What the assistant can do

Twenty-one tools. The full descriptions are in
[`src/nuvo_mcp/tools.py`](../src/nuvo_mcp/tools.py) (the `DESCRIPTIONS` dict),
and the model reads the very same ones.

**Looking**
`list_lists` — projects, areas, tags, saved filters ·
`list_tasks` — tasks filtered by "when", project or tag ·
`today` — what is on for today and what is overdue ·
`search_tasks` — search by title and notes ·
`get_task` — one task in full.

**Creating and changing**
`create_task` · `update_task` · `add_note` — append a dated paragraph to the
notes · `move_task` — into a project, into an area or to the Inbox ·
`create_project` · `create_area`.

**Changing state**
`schedule_task` — Today, This Evening, Anytime, Someday or a date ·
`complete_task` · `reopen_task` · `log_task` — file a finished task in the
Logbook · `trash_task` · `restore_task`.

**Checklists and tags**
`add_checklist_item` · `check_checklist_item` · `tag_task` · `untag_task`.

Deliberately missing: permanent deletion. Emptying the trash is the person's own
job.

## Caveats

- **A key opens the whole database.** There is no "this project yes, that one
  no". Issue a key with the rights that are needed, and revoke it when it is no
  longer needed.
- **The smart lists live in the app.** Through MCP you get filters over fields
  ("when", project, tag, deadline) and `today` separately. Upcoming, Anytime and
  the Logbook are not reimplemented as rules here: a copy would inevitably drift
  away from the original.
- **`uvx` pulls the package from the network on first run.** After that it comes
  from the cache; to update it, `uvx --refresh nuvo-mcp`.
