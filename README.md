# pdsx

general-purpose cli for atproto record operations

📚 **[documentation](https://pdsx.zzstoatzz.io)**

## installation

```bash
uv add pdsx
# or run directly
uvx pdsx --help
# or from GitHub (latest)
uvx --from git+https://github.com/zzstoatzz/pdsx pdsx --help
```

## quick start

**important**: flags like `-r`, `--handle`, `--password` go BEFORE the command (`ls`, `get`, etc.)

```bash
# read anyone's posts (no auth needed)
uvx pdsx -r zzstoatzz.io ls app.bsky.feed.post -o json | jq -r '.[].text'

# update your bio (requires auth)
export ATPROTO_HANDLE=your.handle ATPROTO_PASSWORD=your-app-password
uvx pdsx edit app.bsky.actor.profile/self description='new bio'
```

## features

- crud operations for atproto records (list, get, create, update, delete)
- **batch operations**: delete multiple records concurrently with progress tracking
- **blob upload**: upload images, videos, and other binary content
- **cursor pagination**: paginate through large collections
- **MCP server**: expose operations via [model context protocol](https://modelcontextprotocol.io) for AI agents
- optional auth: reads with `--repo` flag don't require authentication
- shorthand URIs: use `app.bsky.feed.post/abc123` when authenticated
- multiple output formats: compact (default), json, yaml, table
- unix-style aliases: `ls`, `cat`, `rm`, `edit`, `touch`/`add`
- jq-friendly json output
- python 3.10+, type-safe

## MCP server

pdsx includes an MCP server for AI agent integration (e.g., claude code, cursor).

```bash
# add to claude code (read-only)
claude mcp add-json pdsx '{"type": "http", "url": "https://pdsx-by-zzstoatzz.fastmcp.app/mcp"}'

# with authentication for writes
claude mcp add-json pdsx '{
  "type": "http",
  "url": "https://pdsx-by-zzstoatzz.fastmcp.app/mcp",
  "headers": {
    "x-atproto-handle": "your.handle",
    "x-atproto-password": "your-app-password"
  }
}'
```

get an app password at: https://bsky.app/settings/app-passwords

📚 **[full MCP documentation](https://pdsx.zzstoatzz.io/guides/mcp-server)** - local setup, custom PDS, available tools, filtering, and more

### running the MCP server locally

run the MCP server locally with `uvx`:

```bash
uvx --from 'pdsx[mcp]' pdsx-mcp
```

to add it to claude code as a local stdio server:

```bash
claude mcp add pdsx -- uvx --from 'pdsx[mcp]' pdsx-mcp
```

for authenticated writes, use the `-e` flag:

```bash
claude mcp add pdsx -e ATPROTO_HANDLE=your.handle -e ATPROTO_PASSWORD=your-app-password -- uvx --from 'pdsx[mcp]' pdsx-mcp
```

<details>
<summary>usage examples</summary>

### read operations (no auth with -r)

```bash
# list records from any repo (note: -r goes BEFORE ls)
pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 5 -o json

# read someone's bio
pdsx -r zzstoatzz.io ls app.bsky.actor.profile -o json | jq -r '.[0].description'
```

### pagination

```bash
# get first page (note: -r before ls, --cursor after)
pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 2

# output includes cursor if more pages exist, copy it for next command
# next page cursor: 3m5335qycpc2z

# get next page (use actual cursor from previous output)
pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 2 --cursor 3m5335qycpc2z
```

### post with image (end-to-end)

```bash
# download a test image
curl -sL https://picsum.photos/200/200 -o /tmp/test.jpg

# upload image and capture blob reference
pdsx upload-blob /tmp/test.jpg
# copy the blob reference from output, example:
# {"$type":"blob","ref":{"$link":"bafkreif..."},"mimeType":"image/jpeg","size":6344}

# create post with uploaded image (paste your actual blob reference)
pdsx create app.bsky.feed.post \
  text='Posted via pdsx!' \
  'embed={"$type":"app.bsky.embed.images","images":[{"alt":"test image","image":{"$type":"blob","ref":{"$link":"PASTE_YOUR_CID_HERE"},"mimeType":"image/jpeg","size":6344}}]}'
```

### write operations (auth required)

```bash
# update your bio
pdsx edit app.bsky.actor.profile/self description='Building with pdsx!'

# create a simple post
pdsx create app.bsky.feed.post text='Hello from pdsx!'

# delete a post (use the rkey from create output)
pdsx rm app.bsky.feed.post/PASTE_RKEY_HERE
```

### batch operations

```bash
# delete multiple records (runs concurrently)
pdsx rm app.bsky.feed.post/abc123 app.bsky.feed.post/def456 app.bsky.feed.post/ghi789

# delete from file via stdin (the Unix way)
cat uris.txt | pdsx rm

# control concurrency (default: 10)
pdsx rm uri1 uri2 uri3 --concurrency 20

# fail-fast mode (stop on first error)
pdsx rm uri1 uri2 uri3 --fail-fast
```

**note**: when authenticated, use shorthand URIs (`collection/rkey`) instead of full AT-URIs (`at://did:plc:.../collection/rkey`)

</details>

<details>
<summary>output formats</summary>

both `ls` and `cat`/`get` support four output formats:

### compact (default for ls)
```
app.bsky.feed.post (3 records)
3m4ryxwq5dt2i: {"created_at":"2025-11-04T07:25:17.061883+00:00","text":"..."}
```

### json
```bash
pdsx -r zzstoatzz.io ls app.bsky.feed.post -o json | jq '.[].text'
pdsx -r zzstoatzz.io cat app.bsky.feed.post/3m5335qycpc2z -o json
```

### yaml
```bash
pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 3 -o yaml
pdsx -r zzstoatzz.io cat app.bsky.actor.profile/self -o yaml
```

### table (default for cat/get)
```bash
pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 5 -o table
pdsx -r zzstoatzz.io cat app.bsky.actor.profile/self  # default
```

</details>

<details>
<summary>development</summary>

```bash
git clone https://github.com/zzstoatzz/pdsx
cd pdsx
uv sync
uv run pytest
uv run ty check
```

</details>

## license

mit
