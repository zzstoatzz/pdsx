---
name: reading-records
description: Read AT Protocol records and blobs from any repo with pdsx — authenticated or not, including pagination, identity resolution, and fetching blob content. Use when inspecting what an account has published, pulling records out of a PDS, or exploring an unfamiliar lexicon.
user-invocable: true
---

# reading records

<!-- `--prerelease=allow` is required: pdsx pins fastmcp==4.0.0a1, and without
the flag a resolver silently installs 0.1.5 instead of erroring. -->

Every read targets a repo. Public repo data needs no credentials — `-r` is
enough, and works against self-hosted servers because pdsx resolves each
repo's own PDS from its DID document.

```bash
uvx --prerelease=allow pdsx -r zzstoatzz.io ls app.bsky.feed.post
```

## `-r` is required for reads, always

This is the most common surprise: **being authenticated does not imply a
target.** A read with credentials but no `-r` fails rather than defaulting to
your own repo.

```bash
$ pdsx ls app.bsky.feed.post          # even with ATPROTO_HANDLE set
error: -r/--repo is required for read operations
```

Pass your own handle to read your own repo: `pdsx -r you.bsky.social ls …`

Credentials only change *what* you can see (your own non-public data), never
*where* the read goes.

## start by asking what's there

Omit the collection to list the repo's collections. Do this before guessing at
lexicon names — most repos carry records from apps you haven't heard of.

```bash
uvx --prerelease=allow pdsx -r zzstoatzz.io ls
```

## pagination is not automatic — this is the big one

`ls` returns **one page**, default limit 50. It does not follow cursors.

A repo with 144 records answers a default `ls` with 50 and a cursor. If you
treat that page as the whole collection you will draw confident, wrong
conclusions — "their newest post is from January" when the newest is from
last week and simply sits on page two.

The cursor goes to **stderr**, so `-o json` on stdout stays pipeable:

```bash
uvx --prerelease=allow pdsx -r zzstoatzz.io ls app.bsky.feed.post -o json | jq '.[].uri'
# stderr: next page cursor: 3mrgybvq4w22y
```

Follow it explicitly:

```bash
uvx --prerelease=allow pdsx -r zzstoatzz.io ls app.bsky.feed.post --limit 100 --cursor 3mrgybvq4w22y
```

When you need a whole collection, loop until no cursor comes back, or go
straight to the XRPC endpoint:

```bash
curl -s "$PDS/xrpc/com.atproto.repo.listRecords?repo=$DID&collection=$NSID&limit=100&cursor=$CURSOR"
```

**Before claiming anything about "all" or "the latest" of something, confirm
you actually reached the end.** Sorting one page tells you about that page.

## getting a single record

```bash
# full AT-URI
uvx --prerelease=allow pdsx get at://did:plc:xbtmt2zjwlrfegqvch7fboei/app.bsky.feed.post/abc123

# shorthand, with -r supplying the repo
uvx --prerelease=allow pdsx -r zzstoatzz.io get app.bsky.actor.profile/self
```

Shorthand is `collection/rkey`. Profile records always use rkey `self`.

## output formats

`-o` takes `compact` (default), `json`, `yaml`, `table`. Use `json` for
anything programmatic — it is clean on stdout, so `| jq` is safe.

## reading blobs

Blobs are not records and pdsx has no download command. Records carry a blob
*reference*; the bytes live behind `com.atproto.sync.getBlob` on the repo's
own PDS.

```bash
# 1. pull the ref out of the record
CID=$(uvx --prerelease=allow pdsx -r zzstoatzz.io get app.bsky.actor.profile/self -o json \
      | jq -r '.value.avatar.ref."$link"')

# 2. resolve the repo's DID and its PDS
DID=$(curl -s "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=zzstoatzz.io" | jq -r .did)
PDS=$(curl -s "https://plc.directory/$DID" | jq -r '.service[] | select(.id=="#atproto_pds") | .serviceEndpoint')

# 3. fetch the bytes from that PDS, not from bsky.social
curl -s "$PDS/xrpc/com.atproto.sync.getBlob?did=$DID&cid=$CID" -o avatar.jpg
```

The blob lives on the *repo owner's* PDS. Asking a different host for it will
404 even though the CID is valid.

## reading well

- **Prefer DIDs to handles** for anything you store or repeat. Handles are
  rebindable; the DID is the durable identifier.
- **Don't assume bsky.social.** Records live on whatever PDS the DID document
  names. pdsx handles this for you; raw `curl` does not.
- **Read before you write.** To edit a record, fetch it first — see
  [writing-records](../writing-records/SKILL.md), where updates merge into
  what's already there.
- **Unknown lexicons are normal.** A repo may hold records from any app. Read
  one and look at its `$type` rather than assuming a schema.

## MCP tools

When the pdsx MCP server is available, `list_records`, `get_record`,
`describe_repo` and `query` cover the same reads with structured output.
`query` issues arbitrary read-only XRPC calls, which is the escape hatch for
endpoints without a dedicated tool.

The MCP surface has **no pagination helper either** — the same cursor
discipline applies.
