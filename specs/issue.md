## Bug Ticket: Cannot Access Private Repositories via Devin MCP (Not DeepWiki MCP)

### Summary
When Claude Desktop is connected to Devin MCP (Not DeepWiki MCP), private repositories that show as "Indexed" on the dashboard cannot be reached through the API; the response is `Repository not found`. The same operation succeeds for public repositories.

### Environment
- App: Claude Desktop (Devin MCP integration)
- Endpoint: `https://mcp.devin.ai/sse`
- Authentication: Personal API Key obtained from Settings → API Keys (`<API_KEY>`)

### Steps to Reproduce
1. Launch Claude Desktop and connect it to Devin MCP.
2. Configure `claude_desktop_config.json` to use the MCP connection.
3. Attempt to access a private repository via MCP, e.g. `private/repo1` or `private/repo1`.

### Actual Result
- The API returns `Repository not found`, so the private repository content cannot be retrieved.

### Expected Result
- Private repositories that appear as Indexed on the dashboard should also be retrievable via MCP.

### Configurations Tried
**Claude Desktop (failed cases)**
```json
{
  "mcpServers": {
    "devin": {
      "command": "/absolute/path/to/mise",
      "args": [
        "x",
        "node@lts",
        "--",
        "npx",
        "mcp-remote",
        "https://mcp.devin.ai/sse"
      ],
      "env": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

**Claude Desktop (explicit `--header`, all failed)**
```json
{
  // rest of config...
  "args": [
    "mcp-remote",
    "https://mcp.devin.ai/sse",
    "--header",
    "Authorization: Bearer ${AUTH_TOKEN}"
  ],
  "env": {
    "AUTH_TOKEN": "<API_KEY>"
  }
}
```
```json
{
  // rest of config...
  "args": [
    "mcp-remote",
    "https://mcp.devin.ai/sse",
    "--header",
    "Authorization:${AUTH_HEADER}"
  ],
  "env": {
    "AUTH_HEADER": "Bearer <API_KEY>"
  }
}
```
```json
{
  // rest of config...
  "args": [
    "mcp-remote",
    "https://mcp.devin.ai/sse",
    "--header",
    "Authorization:Bearer <API_KEY>"
  ]
}
```
```json
{
  // rest of config...
  "args": [
    "mcp-remote",
    "https://mcp.devin.ai/sse"
  ],
  "header": {
    "Authorization:Bearer <API_KEY>"
  }
}
```

**Windsurf (success)**
```json
{
  "mcpServers": {
    "devin": {
      "serverUrl": "https://mcp.devin.ai/sse",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

**Claude / Claude Code (success)**
```json
{
  "mcpServers": {
    "devin": {
      "type": "http",
      "url": "https://mcp.devin.ai/mcp",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

### Notes
- In Claude Desktop the `Authorization` value is supplied via an environment variable, but it may not propagate correctly into the HTTP headers.
- Windsurf and Claude / Claude Code explicitly set the `Authorization` header and are able to reach private repositories.
- In every configuration example, `<API_KEY>` denotes the same Personal API Key placeholder.
