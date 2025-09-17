# devin-sse-proxy

[![CI](https://github.com/sotayamashita/devin-sse-proxy/actions/workflows/ci.yml/badge.svg)](https://github.com/sotayamashita/devin-sse-proxy/actions/workflows/ci.yml)

`devin-sse-proxy` is a minimal Python-based MCP server that allows Claude Desktop to talk to Devin's SSE transport while reliably passing a Personal API Key. It exists as a temporary workaround for the bug described in [issue.md](./specs/issue.md), where the stock `mcp-remote` client drops custom `Authorization` headers and prevents access to private repositories. Windsurf and Claude Code already work against Devin because they manage headers directly; this proxy fills the gap for Claude Desktop until Devin or Claude ships a native fix.

## How It Works
- Bridges STDIN/STDOUT JSON-RPC from Claude Desktop to Devin's SSE endpoint (`https://mcp.devin.ai/sse`).
- Listens for the `endpoint` SSE event and dynamically switches HTTP POSTs to the provided message URL.
- Persists the `Mcp-Session-Id` response header and attaches it to subsequent requests to keep the session alive.
- Forces `Authorization: Bearer <API key>` on every HTTP call so private repositories remain accessible.

## Requirements
- Python 3.11+ (project is configured for 3.13 via `pyproject.toml`).
- [uv](https://github.com/astral-sh/uv) for dependency management (optional but recommended).
- A Devin Personal API Key with access to the desired repositories.

## Installation
```bash
git clone git@github.com:sotayamashita/devin-sse-proxy.git
uv sync
```
This creates `.venv/` and installs `aiohttp` plus Python stdlib dependencies.

## Running the Proxy
```bash
uv run python main.py --api-key <YOUR_DEVIN_PERSONAL_API_KEY>
```

## Claude Desktop Integration
Edit `~/Library/Application Support/Claude/claude_desktop_config.json` to point the `devin` MCP server at this script.

### Build from source

```json
{
  "mcpServers": {
    "devin": {
      "command": "abosulte/path/to/devin-sse-proxy/.venv/bin/python",
      "args": [
        "abosulte/path/to/devin-sse-proxy/main.py",
        "--api-key",
        "<YOUR_DEVIN_PERSONAL_API_KEY>"
      ],
    }
  }
}
```

### Using the Docker Image

```json
{
  "mcpServers": {
    "devin": {
      "command": "/usr/local/bin/docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "DEVIN_API_KEY=<YOUR_DEVIN_PERSONAL_API_KEY>",
        "ghcr.io/sotayamashita/devin-sse-proxy:latest"
      ]
    }
  }
}
```

## Limitations
- This project is intentionally minimal and will be retired once Devin MCP or Claude Desktop supports API-key forwarding natively.
- No automatic reconnection beyond basic exponential backoff; restart the proxy if Claude Desktop disconnects permanently.
