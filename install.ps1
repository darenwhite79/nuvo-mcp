# Installer for nuvo-mcp on Windows (PowerShell).
#
#   irm https://raw.githubusercontent.com/darenwhite79/nuvo-mcp/main/install.ps1 | iex
#
# Installs uv if it is missing; asks for a key, an address and a client;
# registers the MCP server. Other settings are kept: a file is backed up before
# it is edited. To skip the questions, set $env:NUVO_TOKEN and $env:NUVO_CLIENT
# beforehand.

$ErrorActionPreference = 'Stop'
$RunFrom = 'git+https://github.com/darenwhite79/nuvo-mcp.git'

# ── 1. uv ────────────────────────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host 'uv not found — installing it (astral.sh)…'
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw 'Could not install uv. Install it by hand: https://docs.astral.sh/uv/'
}
Write-Host "uv is here: $(uv --version)"

# ── 2. key and address ───────────────────────────────────────────────────────
$Token = if ($env:NUVO_TOKEN) { $env:NUVO_TOKEN } else { Read-Host 'Nuvo access key (Settings -> Connection)' }
if (-not $Token) { throw 'The server cannot be connected without a key.' }
if (-not $Token.StartsWith('nv_')) { throw "A key has to start with 'nv_'." }
$Url = if ($env:NUVO_URL) { $env:NUVO_URL } else { 'http://127.0.0.1:8000' }

# ── 3. client ────────────────────────────────────────────────────────────────
$Client = $env:NUVO_CLIENT
if (-not $Client) {
  Write-Host ''
  Write-Host 'Where should the server be connected?'
  Write-Host '  1) Claude Code (terminal)'
  Write-Host '  2) Claude Desktop'
  Write-Host '  3) Cursor'
  Write-Host '  4) just print the configuration'
  switch (Read-Host 'Number') {
    '2' { $Client = 'claude-desktop' }
    '3' { $Client = 'cursor' }
    '4' { $Client = 'print' }
    default { $Client = 'claude-code' }
  }
}

function Write-Json($File) {
  $dir = Split-Path $File
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  if (Test-Path $File) { Copy-Item $File "$File.bak-nuvo-$(Get-Date -Format yyyyMMdd-HHmmss)" }
  $data = @{}
  if ((Test-Path $File) -and (Get-Item $File).Length -gt 0) {
    try { $data = Get-Content $File -Raw | ConvertFrom-Json -AsHashtable }
    catch { throw "$File is not JSON, so it was left alone." }
  }
  if (-not $data.mcpServers) { $data.mcpServers = @{} }
  $data.mcpServers.nuvo = @{
    command = 'uvx'
    args    = @('--from', $RunFrom, 'nuvo-mcp')
    env     = @{ NUVO_TOKEN = $Token; NUVO_URL = $Url }
  }
  ($data | ConvertTo-Json -Depth 10) | Set-Content $File -Encoding utf8
  Write-Host "Written to $File"
}

switch ($Client) {
  'claude-code' {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
      claude mcp add nuvo -s user -e "NUVO_TOKEN=$Token" -e "NUVO_URL=$Url" -- uvx --from $RunFrom nuvo-mcp
      Write-Host 'Done. Ask Claude Code: "what do I have today?"'
    } else {
      Write-Host "The 'claude' CLI was not found — printing the configuration."
      $Client = 'print'
    }
  }
  'claude-desktop' { Write-Json "$env:APPDATA\Claude\claude_desktop_config.json"; Write-Host 'Done. Restart Claude Desktop.' }
  'cursor'         { Write-Json "$env:USERPROFILE\.cursor\mcp.json"; Write-Host 'Done. Restart Cursor.' }
}

if ($Client -eq 'print') {
  Write-Host ''
  Write-Host "Paste this into your client's mcp.json (the key is filled in):"
  $cfg = @{ mcpServers = @{ nuvo = @{
    command = 'uvx'; args = @('--from', $RunFrom, 'nuvo-mcp')
    env = @{ NUVO_TOKEN = $Token; NUVO_URL = $Url } } } }
  Write-Host ($cfg | ConvertTo-Json -Depth 10)
}
