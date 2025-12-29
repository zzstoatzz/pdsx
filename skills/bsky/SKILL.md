---
name: bsky
description: Use this when working with BlueSky - fetching threads, reading posts, creating content. Shows you how to use pdsx MCP tools for the task.
---

# BlueSky with pdsx

Use the pdsx MCP tools (`list_records`, `get_record`, `create_record`) for BlueSky tasks.

## IMPORTANT: Avoid Context Flooding

**Always use small limits and project to needed fields.** Large responses will exceed token limits.

```python
# BAD - returns too much data
list_records("app.bsky.feed.post", repo="someone", limit=100)

# GOOD - small limit, only the fields you need
list_records("app.bsky.feed.post", repo="someone", limit=10,
             _filter="[*].{uri: uri, text: value.text, reply: value.reply}")
```

**Rules:**
1. **Start with `limit=10` or less** - never use limit > 20 on first call
2. **Always use `_filter` to select only needed fields** - don't fetch full records
3. **Use `get_record` when you have a URI** - don't list and search
4. **`_filter` runs AFTER fetch** - it reduces output, not what's fetched from the API

## Quick Reference

| Task | Tool | Example |
|------|------|---------|
| get a specific post | `get_record` | `get_record(uri="at://did:plc:xxx/app.bsky.feed.post/abc123")` |
| list posts (small batch) | `list_records` | `list_records("app.bsky.feed.post", repo="handle", limit=10, _filter="[*].{uri: uri, text: value.text}")` |
| get a profile | `get_record` | `get_record(uri="app.bsky.actor.profile/self", repo="handle")` |

## Following Threads

**Start by getting the specific post you have:**

```python
get_record(uri="at://did:plc:xxx/app.bsky.feed.post/abc123")
```

Then get a small sample of the OP's posts to find thread participants:

```python
list_records("app.bsky.feed.post", repo="did:plc:xxx", limit=10,
             _filter="[?value.reply].{uri: uri, reply: value.reply}")
```

Extract DIDs from reply URIs (format: `at://DID/collection/rkey`), then query each participant with small limits.

## Collections

| Collection | Purpose |
|------------|---------|
| `app.bsky.feed.post` | posts |
| `app.bsky.actor.profile` | profile (rkey always `self`) |
| `app.bsky.feed.like` | likes |
| `app.bsky.feed.repost` | reposts |
| `app.bsky.graph.follow` | follows |

## Post Structure

```json
{
  "text": "post text",
  "reply": {
    "root": {"uri": "at://did/collection/rkey", "cid": "bafyrei..."},
    "parent": {"uri": "at://did/collection/rkey", "cid": "bafyrei..."}
  }
}
```

## Useful `_filter` Patterns

```python
# just URIs and text (minimal output)
_filter="[*].{uri: uri, text: value.text}"

# posts with replies only, showing reply info
_filter="[?value.reply].{uri: uri, text: value.text, reply: value.reply}"

# just URIs
_filter="[*].uri"
```

## Creating Posts

```python
create_record("app.bsky.feed.post", {"text": "hello world"})
```

Reply (needs uri AND cid from parent):
```python
create_record("app.bsky.feed.post", {
    "text": "my reply",
    "reply": {
        "root": {"uri": "at://...", "cid": "..."},
        "parent": {"uri": "at://...", "cid": "..."}
    }
})
```
