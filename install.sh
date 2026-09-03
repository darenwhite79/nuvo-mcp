#!/bin/sh
# Installer for nuvo-mcp on macOS and Linux.
#
#   curl -LsSf https://raw.githubusercontent.com/darenwhite79/nuvo-mcp/main/install.sh | sh
#
# What it does: installs uv if it is missing; asks for an access key, an address
# and a client; registers the MCP server with the chosen client. It deletes
# nothing: other settings are kept, and a file is backed up before it is edited.
#
# Running it without questions (for scripts):
#   NUVO_TOKEN=nv_… NUVO_CLIENT=claude-code sh install.sh
# Variables: NUVO_TOKEN (the key), NUVO_URL (the address, 127.0.0.1:8000 by
# default), NUVO_CLIENT (claude-code | claude-desktop | cursor | print).

set -eu

REPO="git+https://github.com/darenwhite79/nuvo-mcp.git"
# The command that starts the server. While the package is not on PyPI, install
# it straight from the repository.
RUN_FROM="$REPO"

say() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }
ask() {
  # ask VARIABLE "question" "default"
  _def="$3"
  if [ -n "$_def" ]; then printf '%s [%s]: ' "$2" "$_def" >&2; else printf '%s: ' "$2" >&2; fi
  read -r _ans </dev/tty || _ans=""
  [ -z "$_ans" ] && _ans="$_def"
  eval "$1=\$_ans"
}

# ── 1. uv ────────────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
  say "uv not found — installing it (astral.sh)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv lands in ~/.local/bin; put it on PATH for this run.
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || { err "Could not install uv. Install it by hand: https://docs.astral.sh/uv/"; exit 1; }
say "uv is here: $(uv --version)"

# ── 2. key and address ───────────────────────────────────────────────────────
TOKEN="${NUVO_TOKEN:-}"
[ -z "$TOKEN" ] && ask TOKEN "Nuvo access key (Settings -> Connection)" ""
case "$TOKEN" in
  nv_*) : ;;
  "") err "The server cannot be connected without a key. Issue one on the Connection screen."; exit 1 ;;
  *) err "A key has to start with 'nv_'. Something extra seems to have been copied in."; exit 1 ;;
esac
URL="${NUVO_URL:-http://127.0.0.1:8000}"

# ── 3. client ────────────────────────────────────────────────────────────────
CLIENT="${NUVO_CLIENT:-}"
if [ -z "$CLIENT" ]; then
  say ""
  say "Where should the server be connected?"
  say "  1) Claude Code (terminal)"
  say "  2) Claude Desktop"
  say "  3) Cursor"
  say "  4) just print the configuration (I will paste it myself)"
  ask _c "Number" "1"
  case "$_c" in
    1) CLIENT=claude-code ;; 2) CLIENT=claude-desktop ;; 3) CLIENT=cursor ;; *) CLIENT=print ;;
  esac
fi

# The configuration object of a single server, as JSON. Written with python: it
# is present wherever uv is, and it does not break someone else's file — it
# reads, adds to it and puts it back, with a backup.
write_json() {
  # write_json FILE  (the mcpServers.nuvo object is added, nothing else is touched)
  _file="$1"
  mkdir -p "$(dirname "$_file")"
  [ -f "$_file" ] && cp "$_file" "$_file.bak-nuvo-$(date +%Y%m%d-%H%M%S)"
  NUVO_FILE="$_file" NUVO_RUN_FROM="$RUN_FROM" NUVO_TOKEN="$TOKEN" NUVO_URL="$URL" \
  python3 - <<'PY'
import json, os, pathlib
path = pathlib.Path(os.environ["NUVO_FILE"])
data = {}
if path.exists() and path.stat().st_size:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise SystemExit(f"{path} is not JSON, so it was left alone. Check it.")
servers = data.setdefault("mcpServers", {})
servers["nuvo"] = {
    "command": "uvx",
    "args": ["--from", os.environ["NUVO_RUN_FROM"], "nuvo-mcp"],
    "env": {"NUVO_TOKEN": os.environ["NUVO_TOKEN"], "NUVO_URL": os.environ["NUVO_URL"]},
}
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(f"Written to {path}")
PY
}

case "$CLIENT" in
  claude-code)
    if command -v claude >/dev/null 2>&1; then
      claude mcp add nuvo -s user -e "NUVO_TOKEN=$TOKEN" -e "NUVO_URL=$URL" \
        -- uvx --from "$RUN_FROM" nuvo-mcp
      say "Done. Ask Claude Code: \"what do I have today?\""
    else
      err "The 'claude' CLI was not found. Install Claude Code, or choose to print the configuration."
      CLIENT=print
    fi
    ;;
  claude-desktop)
    case "$(uname -s)" in
      Darwin) F="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
      *)      F="$HOME/.config/Claude/claude_desktop_config.json" ;;
    esac
    write_json "$F"
    say "Done. Restart Claude Desktop."
    ;;
  cursor)
    write_json "$HOME/.cursor/mcp.json"
    say "Done. Restart Cursor."
    ;;
esac

if [ "$CLIENT" = print ]; then
  say ""
  say "Paste this into your client's mcp.json (the key is filled in):"
  say '{'
  say '  "mcpServers": {'
  say '    "nuvo": {'
  say '      "command": "uvx",'
  say "      \"args\": [\"--from\", \"$RUN_FROM\", \"nuvo-mcp\"],"
  say '      "env": {'
  say "        \"NUVO_TOKEN\": \"$TOKEN\","
  say "        \"NUVO_URL\": \"$URL\""
  say '      }'
  say '    }'
  say '  }'
  say '}'
fi
