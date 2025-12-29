---
name: bsky
description: Use this when working with BlueSky - fetching threads, reading posts, creating content. Shows you how to use pdsx MCP tools for the task.
---

# BlueSky with pdsx

pdsx provides generic ATProto record operations. This skill covers BlueSky-specific patterns.

## Collections

| Collection | Purpose | Key field |
|------------|---------|-----------|
| `app.bsky.feed.post` | posts | `text`, `reply`, `embed` |
| `app.bsky.actor.profile` | profile (rkey always `self`) | `displayName`, `description` |
| `app.bsky.feed.like` | likes | `subject` (strongRef to post) |
| `app.bsky.feed.repost` | reposts | `subject` (strongRef to post) |
| `app.bsky.graph.follow` | follows | `subject` (DID of followed user) |

## Post Structure

Posts reference other posts via `strongRef` (uri + cid pair):

```json
{
  "text": "reply text",
  "reply": {
    "root": {"uri": "at://did:plc:.../app.bsky.feed.post/abc", "cid": "bafyrei..."},
    "parent": {"uri": "at://did:plc:.../app.bsky.feed.post/xyz", "cid": "bafyrei..."}
  }
}
```

- `reply.root` - the thread's original post
- `reply.parent` - the immediate parent being replied to

Quote posts use `embed.record`:

```json
{
  "text": "check this out",
  "embed": {
    "$type": "app.bsky.embed.record",
    "record": {"uri": "at://...", "cid": "bafyrei..."}
  }
}
```

## Following Threads

**The challenge**: pdsx queries one repo at a time. Threads span multiple users.

**Pattern for finding thread participants**:

```bash
# 1. get the root post
pdsx -r did:plc:xxx get app.bsky.feed.post/abc123 -o json

# 2. get OP's posts, filter for replies to this thread
pdsx -r did:plc:xxx ls app.bsky.feed.post -o json --limit 100 \
  | jq '[.[] | select(.reply.root.uri == "at://did:plc:xxx/app.bsky.feed.post/abc123")]'

# 3. extract other participants from reply.parent URIs
... | jq -r '.[].reply.parent.uri' | grep -v "did:plc:xxx" | cut -d'/' -f3 | sort -u

# 4. query each participant's repo for their replies to the thread
```

**With MCP tools and `_filter`**:

```python
# get posts, extract reply parent URIs
list_records("app.bsky.feed.post", repo="did:plc:xxx", _filter="[?reply].reply.parent.uri")
```

**When this gets painful**: Use BlueSky's AppView API instead.

## When to Use AppView APIs

pdsx operates at the ATProto layer (individual repos). BlueSky's AppView provides indexed, cross-repo queries:

| Task | pdsx | AppView |
|------|------|---------|
| read someone's posts | `list_records` | `app.bsky.feed.getAuthorFeed` |
| get a single post | `get_record` | `app.bsky.feed.getPosts` |
| **follow a thread** | manual traversal | `app.bsky.feed.getPostThread` |
| **search posts** | not possible | `app.bsky.feed.searchPosts` |
| get likes on a post | query each liker | `app.bsky.feed.getLikes` |

**Rule of thumb**: If you need data aggregated across repos (thread replies, search, counts), use AppView. If you need to read/write specific records, use pdsx.

AppView base URL: `https://public.api.bsky.app/xrpc/`

```bash
# get full thread via AppView
curl "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://did:plc:xxx/app.bsky.feed.post/abc123&depth=10"
```

## Creating Posts

Simple post:
```python
create_record("app.bsky.feed.post", {"text": "hello world"})
```

Reply:
```python
create_record("app.bsky.feed.post", {
    "text": "my reply",
    "reply": {
        "root": {"uri": "at://...", "cid": "..."},
        "parent": {"uri": "at://...", "cid": "..."}
    }
})
```

**Facets** (links, mentions) require byte indices:
```python
text = "check out example.com"
create_record("app.bsky.feed.post", {
    "text": text,
    "facets": [{
        "index": {"byteStart": 10, "byteEnd": 21},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://example.com"}]
    }]
})
```

## Extracting URIs from Records

The `_filter` parameter uses JMESPath:

```python
# all URIs from reply fields
list_records(..., _filter="[?reply].{root: reply.root.uri, parent: reply.parent.uri}")

# just the text
list_records(..., _filter="[*].text")

# posts mentioning a specific DID
list_records(..., _filter="[?contains(to_string(@), 'did:plc:target')]")
```

## Common Gotchas

1. **strongRef requires both uri AND cid** - you can't just use the URI when creating replies
2. **byte indices, not character indices** - facets use UTF-8 byte positions
3. **profile rkey is always `self`** - `app.bsky.actor.profile/self`
4. **no cross-repo queries in pdsx** - that's what AppViews are for
