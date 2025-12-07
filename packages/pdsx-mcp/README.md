# pdsx-mcp

MCP server for pdsx atproto record operations.

## hosted instance

```bash
claude mcp add-json pdsx '{
  "type": "http",
  "url": "https://pdsx-by-zzstoatzz.fastmcp.app/mcp",
  "headers": {
    "x-atproto-handle": "your.handle",
    "x-atproto-password": "your-app-password"
  }
}'
```

## local usage

```bash
ATPROTO_HANDLE=your.handle ATPROTO_PASSWORD=your-app-password pdsx-mcp
```

## tools

| tool | auth required | description |
|------|--------------|-------------|
| `list_records` | only without `repo` | list records in a collection |
| `get_record` | only without `repo` | get a specific record |
| `create_record` | yes | create a new record |
| `update_record` | yes | update an existing record |
| `delete_record` | yes | delete a record |

all tools support jmespath filtering via `_filter` parameter.

## license

MIT
