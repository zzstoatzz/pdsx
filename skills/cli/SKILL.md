---
name: cli
description: Use the pdsx CLI for ATProto record operations. Requires auth for writes, supports batch operations via stdin.
---

# pdsx CLI

Use `uvx pdsx` (or `uv run pdsx` for local dev) for ATProto record operations.

## Authentication

Reads don't need auth, just `-r/--repo`. Writes need `--handle` and `--password`:

```bash
# reads - no auth
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post

# writes - auth required
uvx pdsx --handle you.bsky.social --password xxxx-xxxx create app.bsky.feed.post text='hello'
```

You can also set env vars: `ATPROTO_HANDLE`, `ATPROTO_PASSWORD`

## Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `list` | `ls` | list records in a collection |
| `get` | `cat` | get a specific record |
| `create` | `touch`, `add` | create record(s) |
| `update` | `edit` | update record(s) |
| `delete` | `rm` | delete record(s) |
| `upload-blob` | - | upload image/video |
| `whoami` | `me`, `identity` | show authenticated identity |

## Examples

```bash
# list posts from someone
uvx pdsx -r zzstoatzz.io ls app.bsky.feed.post

# get a specific post
uvx pdsx get at://did:plc:xxx/app.bsky.feed.post/abc123

# get someone's profile
uvx pdsx -r zzstoatzz.io get app.bsky.actor.profile/self

# create a post
uvx pdsx --handle you.bsky.social --password $APP_PASSWORD create app.bsky.feed.post text='hello from pdsx'

# check who you're authenticated as
uvx pdsx --handle you.bsky.social --password $APP_PASSWORD whoami

# delete a post
uvx pdsx --handle you.bsky.social --password $APP_PASSWORD rm at://did:plc:xxx/app.bsky.feed.post/abc123
```

## Batch Operations

Pipe JSONL to stdin for batch operations:

```bash
# batch create
echo '{"text":"post 1"}
{"text":"post 2"}' | uvx pdsx --handle ... create app.bsky.feed.post

# batch delete
echo 'at://did:plc:xxx/app.bsky.feed.post/abc123
at://did:plc:xxx/app.bsky.feed.post/def456' | uvx pdsx --handle ... rm

# batch update (JSONL with uri field)
echo '{"uri":"at://...","text":"updated text"}' | uvx pdsx --handle ... update
```

## Output Formats

Use `-o/--output` for different formats:

```bash
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post -o json
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post -o yaml
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post -o table
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post -o compact  # default for list
```

## Common Collections

| Collection | Purpose |
|------------|---------|
| `app.bsky.feed.post` | posts |
| `app.bsky.actor.profile` | profile (rkey is `self`) |
| `app.bsky.feed.like` | likes |
| `app.bsky.feed.repost` | reposts |
| `app.bsky.graph.follow` | follows |
