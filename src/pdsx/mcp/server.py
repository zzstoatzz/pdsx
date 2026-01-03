"""pdsx MCP server implementation using fastmcp."""

import json
from typing import Any

from fastmcp import FastMCP

from pdsx._internal.operations import (
    create_record as _create_record,
)
from pdsx._internal.operations import (
    delete_record as _delete_record,
)
from pdsx._internal.operations import (
    get_record as _get_record,
)
from pdsx._internal.operations import (
    list_records as _list_records,
)
from pdsx._internal.operations import (
    update_record as _update_record,
)
from pdsx._internal.resolution import URIParts
from pdsx.mcp._types import (
    CreateResponse,
    DeleteResponse,
    RecordResponse,
    UpdateResponse,
)
from pdsx.mcp.client import (
    AuthenticationRequired,
    get_atproto_client,
    get_repo_from_context,
)
from pdsx.mcp.filterable import filterable
from pdsx.mcp.middleware import AtprotoAuthMiddleware

# response size limits to prevent context flooding in LLM clients
MAX_LIMIT = 25  # max records per request (can paginate for more)
MAX_RESPONSE_CHARS = 30000  # truncate responses larger than this

mcp = FastMCP("pdsx")

mcp.add_middleware(AtprotoAuthMiddleware())


def _clean_value(value: Any) -> dict[str, Any]:
    """clean up a record value for semantic density.

    removes:
    - null fields (embed: null, labels: null, etc.)
    - redundant $type fields
    - byte indices from facets (keeps just links/mentions)
    - verbose reply structure (keeps just uris)
    """
    # convert to plain dict - Pydantic models use model_dump, DotDict uses to_dict
    # note: DotDict has model_dump=None (not callable), so check callable()
    if hasattr(value, "model_dump") and callable(value.model_dump):
        value = value.model_dump(mode="json", by_alias=True)
    elif hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()

    if not isinstance(value, dict):
        return {"raw": value}

    result: dict[str, Any] = {}

    for k, v in value.items():
        # skip null values
        if v is None:
            continue

        # skip $type - we already know the collection
        if k == "$type":
            continue

        # simplify facets: extract just the links/mentions
        if k == "facets" and isinstance(v, list):
            links = []
            mentions = []
            for facet in v:
                for feature in facet.get("features", []):
                    ftype = feature.get("$type", "")
                    if "link" in ftype and "uri" in feature:
                        links.append(feature["uri"])
                    elif "mention" in ftype and "did" in feature:
                        mentions.append(feature["did"])
            if links:
                result["links"] = links
            if mentions:
                result["mentions"] = mentions
            continue

        # simplify reply: just keep parent and root URIs
        if k == "reply" and isinstance(v, dict):
            reply_info: dict[str, str] = {}
            if "parent" in v and isinstance(v["parent"], dict):
                reply_info["parent"] = v["parent"].get("uri", "")
            if "root" in v and isinstance(v["root"], dict):
                reply_info["root"] = v["root"].get("uri", "")
            if reply_info:
                result["reply"] = reply_info
            continue

        # skip langs unless it's interesting (multiple or non-english)
        if k == "langs":
            if isinstance(v, list) and (len(v) > 1 or (v and v[0] != "en")):
                result[k] = v
            continue

        # keep everything else
        result[k] = v

    return result


def _truncate_list_response(
    records: list[RecordResponse],
    total_fetched: int,
    has_more: bool,
) -> list[RecordResponse] | dict[str, Any]:
    """truncate list response if it exceeds size limits.

    returns either the original list or a dict with truncated results and a message.
    """
    # serialize to check size
    try:
        response_json = json.dumps(records, default=str)
    except (TypeError, ValueError):
        return records

    if len(response_json) <= MAX_RESPONSE_CHARS:
        return records

    # truncate by removing records until under limit
    truncated = list(records)
    while truncated and len(json.dumps(truncated, default=str)) > MAX_RESPONSE_CHARS:
        truncated.pop()

    shown = len(truncated)
    msg = f"response truncated: showing {shown} of {total_fetched} records"
    if has_more:
        msg += " (more available via cursor)"
    msg += '. use _filter to select specific fields, e.g. _filter="[*].{uri: uri, text: value.text}"'

    return {
        "records": truncated,
        "truncated": True,
        "message": msg,
        "shown": shown,
        "fetched": total_fetched,
    }


# -----------------------------------------------------------------------------
# prompts
# -----------------------------------------------------------------------------


@mcp.prompt("usage_guide")  # type: ignore[call-non-callable]
def usage_guide() -> str:
    """instructions for using pdsx MCP tools."""
    return """\
# pdsx MCP server usage guide

pdsx provides tools for atproto record operations (bluesky, etc).

## authentication

- **read operations**: no auth needed, just pass `repo` parameter
- **write operations** (create, update, delete): require auth

to authenticate for writes, set these headers when configuring the MCP server:
- `x-atproto-handle`: your atproto handle (e.g., 'you.bsky.social')
- `x-atproto-password`: your atproto app password (NOT your main password!)

get an app password at: https://bsky.app/settings/app-passwords

## common collections

- `app.bsky.feed.post` - posts/skeets
- `app.bsky.actor.profile` - user profile (rkey is always 'self')
- `app.bsky.feed.like` - likes
- `app.bsky.feed.repost` - reposts
- `app.bsky.graph.follow` - follows

## uri formats

records are identified by AT-URIs:
- full: `at://did:plc:abc123/app.bsky.feed.post/xyz789`
- shorthand (when authenticated): `app.bsky.feed.post/xyz789`

## filtering results

list_records and get_record support a `_filter` parameter with jmespath:
- `[*].uri` - extract just URIs
- `[*].{uri: uri, text: value.text}` - select specific fields
- `[?value.text != null]` - filter items

see https://jmespath.org for full syntax.
"""


@mcp.prompt("create_post_guide")  # type: ignore[call-non-callable]
def create_post_guide() -> str:
    """instructions for creating posts."""
    return """\
# creating posts with pdsx

## simple text post

```
create_record(
    collection="app.bsky.feed.post",
    record={"text": "hello from pdsx!"}
)
```

## post with link

```
create_record(
    collection="app.bsky.feed.post",
    record={
        "text": "check out pdsx.zzstoatzz.io",
        "facets": [{
            "index": {"byteStart": 10, "byteEnd": 28},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": "https://pdsx.zzstoatzz.io"}]
        }]
    }
)
```

## post with mention

```
create_record(
    collection="app.bsky.feed.post",
    record={
        "text": "@someone.bsky.social hello!",
        "facets": [{
            "index": {"byteStart": 0, "byteEnd": 20},
            "features": [{"$type": "app.bsky.richtext.facet#mention", "did": "did:plc:..."}]
        }]
    }
)
```

note: for mentions, you need to resolve the handle to a DID first.
the createdAt field is auto-added if not provided.
"""


# -----------------------------------------------------------------------------
# tools
# -----------------------------------------------------------------------------


@mcp.tool
@filterable
async def list_records(
    collection: str,
    limit: int = 10,
    repo: str | None = None,
    cursor: str | None = None,
) -> list[RecordResponse] | dict[str, Any]:
    """list records in a collection.

    examples:
    - list_records("app.bsky.feed.post", repo="zzstoatzz.io") - list someone's posts
    - list_records("app.bsky.actor.profile", repo="did:plc:...") - list by DID

    args:
        collection: the collection to list (e.g., 'app.bsky.feed.post')
        limit: max records to return (default 10, max 25)
        repo: handle or DID to read from (required)
        cursor: pagination cursor from previous response

    returns:
        list of records with uri, cid, and value fields
    """
    # cap limit to prevent context flooding
    effective_limit = min(limit, MAX_LIMIT)

    repo_to_use = repo or get_repo_from_context()
    if not repo_to_use:
        raise ValueError(
            "repo parameter is required. example: "
            'list_records("app.bsky.feed.post", repo="someone.bsky.social")'
        )

    async with get_atproto_client(
        require_auth=False,
        target_repo=repo_to_use,
    ) as client:
        response = await _list_records(
            client, collection, effective_limit, repo=repo_to_use, cursor=cursor
        )
        records = [
            RecordResponse(uri=r.uri, cid=r.cid, value=_clean_value(r.value))
            for r in response.records
        ]
        return _truncate_list_response(
            records,
            total_fetched=len(records),
            has_more=response.cursor is not None,
        )


@mcp.tool
@filterable
async def get_record(
    uri: str,
    repo: str | None = None,
) -> RecordResponse:
    """get a specific record by uri.

    examples:
    - get_record("at://did:plc:.../app.bsky.feed.post/abc123")
    - get_record("app.bsky.actor.profile/self", repo="zzstoatzz.io") - someone's profile

    args:
        uri: full AT-URI or shorthand (collection/rkey)
        repo: when using shorthand uri, the repo to read from (required for shorthand)

    returns:
        record with uri, cid, and value fields
    """
    repo_to_use = repo or get_repo_from_context()
    is_full_uri = uri.startswith("at://")

    # for shorthand URIs, repo is required
    if not is_full_uri and not repo_to_use:
        raise ValueError(
            "repo parameter is required for shorthand URIs. example: "
            'get_record("app.bsky.actor.profile/self", repo="someone.bsky.social")'
        )

    # determine target repo for PDS discovery
    target_repo = repo_to_use
    if is_full_uri and not target_repo:
        # extract repo from at://repo/collection/rkey
        target_repo = uri.replace("at://", "").split("/")[0]

    async with get_atproto_client(
        require_auth=False,
        target_repo=target_repo,
    ) as client:
        response = await _get_record(client, uri, repo=repo_to_use)
        return RecordResponse(
            uri=response.uri, cid=response.cid, value=_clean_value(response.value)
        )


@mcp.tool
async def create_record(
    collection: str,
    record: dict[str, Any],
) -> CreateResponse:
    """create a new record. requires authentication.

    args:
        collection: the collection to create in (e.g., 'app.bsky.feed.post')
        record: the record data. $type and createdAt are auto-added if missing.

    returns:
        dict with uri and cid of created record
    """
    async with get_atproto_client(
        require_auth=True,
        operation="creating a record",
    ) as client:
        response = await _create_record(client, collection, record)
        return CreateResponse(uri=response.uri, cid=response.cid)


@mcp.tool
async def update_record(
    uri: str,
    updates: dict[str, Any],
) -> UpdateResponse:
    """update an existing record. requires authentication.

    fetches the current record, merges your updates, and puts it back.

    args:
        uri: full AT-URI or shorthand (collection/rkey)
        updates: fields to update (merged with existing record)

    returns:
        dict with uri and cid of updated record
    """
    async with get_atproto_client(
        require_auth=True,
        operation="updating a record",
    ) as client:
        response = await _update_record(client, uri, updates)
        return UpdateResponse(uri=response.uri, cid=response.cid)


@mcp.tool
async def delete_record(uri: str) -> DeleteResponse:
    """delete a record. requires authentication.

    examples:
    - delete_record("app.bsky.feed.post/abc123")
    - delete_record("at://did:plc:.../app.bsky.feed.post/abc123")

    args:
        uri: full AT-URI or shorthand (collection/rkey)

    returns:
        confirmation with deleted uri
    """
    async with get_atproto_client(
        require_auth=True,
        operation="deleting a record",
    ) as client:
        # parse uri to get parts for confirmation
        parts = URIParts.from_uri(uri, client.me.did if client.me else None)
        await _delete_record(client, uri)
        return DeleteResponse(
            deleted=f"at://{parts.repo}/{parts.collection}/{parts.rkey}"
        )


# -----------------------------------------------------------------------------
# resources
# -----------------------------------------------------------------------------


@mcp.resource("pdsx://me")
async def me_resource() -> str:
    """current authenticated user identity."""
    try:
        async with get_atproto_client(require_auth=True) as client:
            if client.me:
                return f"authenticated as {client.me.handle} ({client.me.did})"
            return "authenticated but no user info available"
    except AuthenticationRequired:
        return "not authenticated - set x-atproto-handle and x-atproto-password headers"


# -----------------------------------------------------------------------------
# entrypoint
# -----------------------------------------------------------------------------


def main() -> None:
    """run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
