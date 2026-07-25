---
name: writing-records
description: Create, update and delete AT Protocol records with pdsx, including blob upload and batch operations over JSONL. Covers what the server fills in for you, how updates merge rather than replace, and how to verify a write actually did what you meant.
user-invocable: true
---

# writing records

Writes always go to **your own repo** — the authenticated account. There is no
`-r` for writes; the credentials decide the target.

```bash
export ATPROTO_HANDLE=you.bsky.social ATPROTO_PASSWORD=xxxx-xxxx
uvx pdsx create app.bsky.feed.post text='hello'
```

Use an **app password**, never your account password. Writes reach whatever PDS
your DID document names — pdsx resolves it, so self-hosted accounts need no
extra flags.

## check who you are before you write

The single most valuable habit here. Credentials in the environment are easy to
get wrong, and a write aimed at the wrong account is not always obvious
afterward.

```bash
uvx pdsx whoami
# zzstoatzz.io (did:plc:xbtmt2zjwlrfegqvch7fboei)
```

If that DID isn't the repo you meant to modify, stop.

## what gets filled in for you

`create` adds two things when you omit them:

- `$type` — set to the collection NSID
- `createdAt` — set to now, RFC 3339 with a `Z` suffix

So `create app.bsky.feed.post text='hi'` really writes
`{"$type": "app.bsky.feed.post", "text": "hi", "createdAt": "…"}`.

Pass either explicitly to override. Preserve the original `createdAt` when
re-creating a record you want to keep in place chronologically.

`--rkey` sets the record key; omit it for a generated TID. Use it for
singleton records — a profile is always rkey `self`.

## update merges, it does not replace

`update` reads the current record, merges your fields over it, and puts the
result back. Fields you don't mention survive.

```bash
uvx pdsx edit app.bsky.actor.profile/self description='new bio'
# displayName, avatar, banner all still there
```

Two consequences worth internalizing:

- **You cannot remove a field with `update`.** Setting it empty stores an empty
  value; it does not delete the key. To genuinely drop a field, read the
  record, remove the key, and `com.atproto.repo.putRecord` the whole value.
- **Merging is shallow.** Supplying a nested object replaces that whole object,
  not just the keys inside it.

## delete tells you when there was nothing there

`deleteRecord` is idempotent at the protocol level — the server returns success
whether or not the record existed. pdsx checks first, so a delete that removed
nothing is reported as a failure rather than a success:

```bash
$ pdsx rm app.bsky.feed.post/never-existed
error: no record at app.bsky.feed.post/never-existed   # exit 1
```

Treat a non-zero exit here as a real signal — usually wrong rkey, wrong
collection, or credentials for a different account than you assumed.

## blobs: upload first, then reference

A blob has to exist on the PDS before a record can point at it. Upload returns
the reference to embed.

```bash
uvx pdsx upload-blob avatar.jpg
```

```json
{
  "$type": "blob",
  "ref": { "$link": "bafkrei…" },
  "mimeType": "image/jpeg",
  "size": 999459
}
```

Paste that object whole into the record field that expects a blob. Don't
hand-assemble one from a CID you found elsewhere — `size` and `mimeType` are
part of the reference and the PDS checks them.

Blobs are reference-counted: one that no record points at is garbage after
upload. Upload, then write the record.

## batch operations

Omit the positional arguments and pdsx reads **JSONL from stdin**, running up
to `--concurrency` operations at once (default 10). By default a failure is
recorded and the run continues; `--fail-fast` stops at the first one.

```bash
# create many
printf '%s\n' '{"text":"post 1"}' '{"text":"post 2"}' \
  | uvx pdsx create app.bsky.feed.post

# update many — each line needs a uri
printf '%s\n' '{"uri":"at://…/abc","text":"fixed"}' \
  | uvx pdsx update

# delete many — plain AT-URIs, one per line
printf '%s\n' 'at://…/abc' 'at://…/def' | uvx pdsx rm
```

This composes with reads. Build the URI list, **look at it**, then pipe:

```bash
uvx pdsx -r you.bsky.social ls app.bsky.feed.post -o json \
  | jq -r '.[] | select(.value.text | test("^test ")) | .uri' > doomed.txt

wc -l doomed.txt && head doomed.txt      # confirm the set before acting
uvx pdsx rm < doomed.txt
```

Never pipe a filter straight into `rm`. The list is cheap to inspect and the
delete is not reversible.

## validation, and how to check you got it right

pdsx does not validate against lexicons before sending. The PDS validates
records whose lexicon it knows and generally accepts records it doesn't, so a
malformed record in a niche collection can be stored happily and then be
useless to every consumer.

Verify by reading back rather than trusting the write:

```bash
uvx pdsx create app.bsky.feed.post text='hello'      # note the returned uri
uvx pdsx -r you.bsky.social get app.bsky.feed.post/<rkey> -o json
```

Compare against a record that already works — the strongest check available:

```bash
# see how a real record of this type is shaped before writing your own
uvx pdsx -r someone.bsky.social ls app.bsky.feed.post --limit 1 -o json
```

Shapes that are easy to get wrong:

- **strongRef needs both `uri` and `cid`.** Replies and quotes carry
  `{"uri": …, "cid": …}`; a uri alone is invalid.
- **Facet indices are UTF-8 byte offsets, not character offsets.** Any
  non-ASCII text earlier in the string shifts them.
- **Timestamps are RFC 3339.** Match what the collection already uses.
- **Rich values need real JSON.** `key=value` pairs are strings; for nested
  objects, pipe JSONL instead.

## norms

- Prefer one deliberate write to a speculative loop. Records are public and
  federated — deletion does not un-send them to anyone already subscribed.
- Don't write test data into a production repo. Use a throwaway account.
- Batch deletes deserve a dry run every time.
- If a write's outcome surprises you, `whoami` first.
