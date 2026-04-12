---
name: smoke-test
description: Verify CLI, SDK, and MCP interfaces are consistent. Use after changing any operation's signature, adding parameters, or cutting a release.
compatibility: Requires uv and a local pdsx dev install
---

# pdsx smoke test

Verify that all three interfaces (SDK, CLI, MCP) expose the same parameters and behave consistently.

## How to run

For each operation (create, update, delete, get, list), check three things:

1. **SDK signature** — inspect the function signature in `src/pdsx/_internal/operations.py`
2. **CLI flags** — run `uv run pdsx <command> --help` and check the argument parser in `src/pdsx/cli.py`
3. **MCP tool schema** — inspect the tool parameters via:
   ```python
   import asyncio, json
   from pdsx.mcp.server import mcp

   async def main():
       tools = await mcp._tool_manager.get_tools()
       for name, t in tools.items():
           print(f"{name}: {json.dumps(t.parameters, indent=2)}")

   asyncio.run(main())
   ```

## What to check

### Parameter consistency

Every user-facing parameter on an SDK function should appear in both the CLI and MCP tool.

| SDK (`operations.py`) | CLI (`cli.py`) | MCP (`mcp/server.py`) |
|----------------------|----------------|----------------------|
| function kwarg | argparse argument | tool function param |

Cross-reference the three source files directly. Read them — don't guess from help text alone.

### Batch consistency

Batch operations live in `src/pdsx/_internal/batch.py`. When a new parameter is added to an SDK function:

- `batch_create` should support per-record values (via a parallel list)
- `read_records_from_stdin` should extract the field from JSONL input (like `rkey` and `uri` are extracted)
- The CLI's `async_main` should thread batch params through correctly

### Tests exist

Every SDK operation should have a corresponding test class in `tests/test_operations.py`:

```
TestGetRecord, TestCreateRecord, TestUpdateRecord, TestDeleteRecord, TestListRecords, TestDescribeRepo
```

If one is missing, flag it.

### Schema matches code

The MCP tool schema (from `t.parameters`) should include all optional params from the SDK function. If a param exists in the Python function signature but not in the JSON schema, the MCP server isn't exposing it to clients.

## Smoke test commands

Run these to verify basic functionality (reads, no auth needed):

```bash
# CLI reads
uv run pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 2
uv run pdsx -r zzstoatzz.io get app.bsky.actor.profile/self
uv run pdsx -r zzstoatzz.io ls  # describe repo

# CLI help for each write command
uv run pdsx create --help
uv run pdsx update --help
uv run pdsx delete --help

# version
uv run pdsx --version
```

## Current operations and their parameters

Keep this table updated when parameters change.

| Operation | SDK params | CLI flags | MCP params |
|-----------|-----------|-----------|------------|
| `create_record` | `collection`, `record`, `rkey` | `collection`, `fields`, `--rkey`, `--concurrency`, `--fail-fast` | `collection`, `record`, `rkey` |
| `update_record` | `uri`, `updates` | `uri`, `fields`, `--concurrency`, `--fail-fast` | `uri`, `updates` |
| `delete_record` | `uri` | `uris`, `--concurrency`, `--fail-fast` | `uri` |
| `get_record` | `uri`, `repo` | `uri`, `-o` | `uri`, `repo` |
| `list_records` | `collection`, `limit`, `repo`, `cursor` | `collection`, `--limit`, `--cursor`, `-o` | `collection`, `limit`, `repo`, `cursor` |
| `describe_repo` | `repo` | (via `ls` without collection) | `repo` |

## When to run this

- After adding a parameter to any operation
- After modifying CLI argument parsing
- After changing MCP tool signatures
- Before cutting a release
