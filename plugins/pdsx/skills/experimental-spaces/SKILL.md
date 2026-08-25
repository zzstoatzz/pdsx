---
name: experimental-spaces
description: Read permissioned data (com.atproto.space.*) with pdsx. Experimental and served by almost no PDS — use when working with private records in a space, or when you need to know whether a given PDS supports permissioned data at all.
user-invocable: true
---

# experimental: permissioned spaces

> **Experimental.** The [permissioned-data proposal][proposal] is still moving,
> and almost no PDS implements it. Expect the shape of this to change.

[proposal]: https://github.com/bluesky-social/proposals/tree/main/0016-permissioned-data

`pdsx spaces` needs **0.1.7 or newer** — check with `pdsx --version` if the
subcommand is missing.

Permissioned data lives outside the public repo. Records in a *space* are not
in `listRecords`, do not appear on the firehose, and require a credential to
read. pdsx exposes the read side:

```bash
pdsx spaces ls                                  # spaces you own or write to
pdsx spaces records --space <uri> --repo <did>  # records in one space
pdsx spaces get --space <uri> --repo <did> --collection <nsid> --rkey <rkey>
```

All of these require authentication. Reads are scoped to the authenticated
account.

## most PDSes will say no — and that's a normal answer

Assume the target does not support this. `spaces ls` reports the reason and
exits **0** with an empty result, because "you have no spaces here" is an
honest answer as long as it says why:

```bash
$ pdsx spaces ls
permissioned data unavailable: https://pds.example does not serve
permissioned data (it may be unimplemented, or disabled by the operator)
# exit 0

$ pdsx spaces ls -o json
{ "supported": false, "spaces": [] }
```

Branch on `supported` rather than on an empty list — an empty `spaces` array
means something different on a PDS that *does* serve the namespace.

`spaces records` and `spaces get` name a specific space, so on an unsupporting
PDS they exit **1** instead. There is no honest empty answer to "give me this
record."

## unsupported is not the same as not-found

On a PDS that *does* serve permissioned data, ordinary failures come back as
themselves:

```bash
$ pdsx spaces get --space at://… --rkey does-not-exist
error: RecordNotFound: Record not found          # exit 1

$ pdsx spaces records --space at://…/no-such-space --repo did:plc:…
error: NotPermitted: Not permitted to read this space
```

Never read a 404 as "this PDS can't do permissioned data" — a working host
returns 404 for a record that simply isn't there.

## you cannot detect support without credentials

PDS implementations run auth middleware *before* method dispatch, so an
anonymous probe returns 401 whether or not the namespace exists. There is no
way to feature-detect from outside.

The authoritative signal is an **authenticated** call returning
`501 MethodNotImplemented`. And even that cannot distinguish a server that
never implemented permissioned data from one where the operator switched it
off — the wire genuinely doesn't say. That's why the message names both.

## space URIs

```
at://{authorityDid}/space/{spaceType}/{skey}
```

A record inside a space appends the author DID, collection and rkey to that
root. `--repo` is the **writer's** DID within the space, not the space
authority — in a single-writer space they are the same, which makes it easy to
miss when they aren't.

Get both from `spaces ls -o json` rather than assembling them by hand.

## reading efficiently

`--exclude-values` returns collection, rkey and CID without materializing
record JSON — use it to survey a space before pulling content:

```bash
pdsx spaces records --space at://… --repo did:plc:… --exclude-values -o json
```

Both `records` and `ls` paginate with `--cursor`, same discipline as
[reading-records](../reading-records/SKILL.md): one page at a time, and the
absence of a cursor is what tells you you're done.

## what is not here

Writes. `createRecord`, `putRecord`, `deleteRecord` and the `simplespace`
membership surface are not implemented in pdsx. Reads only, while the proposal
settles.

Blobs in a space are fetched through `com.atproto.space.getBlob` and are
deliberately excluded from space repo exports — pdsx does not wrap that yet.
