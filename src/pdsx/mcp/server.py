"""pdsx MCP server implementation using fastmcp."""

import json
from typing import Any

import httpx
from fastmcp import FastMCP

from pdsx._internal.operations import (
    create_record as _create_record,
)
from pdsx._internal.operations import (
    delete_record as _delete_record,
)
from pdsx._internal.operations import (
    describe_repo as _describe_repo,
)
from pdsx._internal.operations import (
    get_record as _get_record,
)
from pdsx._internal.operations import (
    list_records as _list_records,
)
from pdsx._internal.operations import (
    query as _query,
)
from pdsx._internal.operations import (
    update_record as _update_record,
)
from pdsx._internal.resolution import (
    URIParts,
    discover_pds,
    normalize_service_url,
)
from pdsx.mcp._types import (
    CreateResponse,
    DeleteResponse,
    IdentityResponse,
    RecordResponse,
    RepoDescriptionResponse,
    UpdateResponse,
)
from pdsx.mcp.client import (
    AuthenticationRequired,
    get_atproto_client,
    get_repo_from_context,
    resolve_pds_url,
)
from pdsx.mcp.middleware import AtprotoAuthMiddleware

# response size limits to prevent context flooding in LLM clients
MAX_LIMIT = 25  # max records per request (can paginate for more)
MAX_RESPONSE_CHARS = 30000  # truncate responses larger than this

# default target for app.bsky.* read queries that aren't tied to a single PDS
PUBLIC_APPVIEW = "https://public.api.bsky.app"

# explicit allowlist for `query(..., authenticated=True)`. authenticated reads
# can expose private data (DMs via `chat.bsky.convo.*`, prefs, etc.), so the
# authority axis is opt-in *and* allowlisted — safe by default. extending the
# allowlist is intentional: a new entry here is a deliberate decision that
# this NSID's response is acceptable for an agentic caller to read with the
# operator's session. start narrow; add only on demonstrated need.
AUTHENTICATED_QUERY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "app.bsky.notification.listNotifications",
        "app.bsky.notification.getUnreadCount",
    }
)

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

    return {
        "records": truncated,
        "truncated": True,
        "message": msg,
        "shown": shown,
        "fetched": total_fetched,
    }


def _truncate_query_response(result: dict[str, Any]) -> dict[str, Any]:
    """trim an oversized query response so it doesn't flood the client context.

    trims the largest list-valued field (e.g. listRepos' 'repos') until the
    serialized response fits, and annotates what was dropped.
    """
    try:
        if len(json.dumps(result, default=str)) <= MAX_RESPONSE_CHARS:
            return result
    except (TypeError, ValueError):
        return result

    list_keys = [k for k, v in result.items() if isinstance(v, list)]
    if not list_keys:
        return {
            "truncated": True,
            "message": f"response exceeded {MAX_RESPONSE_CHARS} chars",
        }

    key = max(list_keys, key=lambda k: len(result[k]))
    original_len = len(result[key])
    items = list(result[key])
    trimmed = dict(result)
    while (
        items
        and len(json.dumps({**trimmed, key: items}, default=str)) > MAX_RESPONSE_CHARS
    ):
        items = items[:-1]

    trimmed[key] = items
    trimmed["truncated"] = True
    trimmed["message"] = (
        f"trimmed '{key}' to {len(items)} of {original_len} items "
        f"(response exceeded {MAX_RESPONSE_CHARS} chars; paginate with cursor)"
    )
    return trimmed


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

## read-only queries (sync, identity, server, app.bsky getters)

for read methods that aren't record CRUD, use `query` — GET-only and
unauthenticated, so it can never write or act as you:

- `query("com.atproto.sync.listRepos", host="pds.zat.dev")` — who's on a PDS
- `query("com.atproto.identity.resolveHandle", params={"handle": "alice.bsky.social"})`
- `query("app.bsky.actor.getProfile", params={"actor": "alice.bsky.social"})`

target a specific user's PDS with `repo=`, a specific host with `host=`, or
neither (defaults to the public appview for `app.bsky.*` getters).

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

    repo_to_use = repo or await get_repo_from_context()
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
async def describe_repo(
    repo: str,
) -> RepoDescriptionResponse:
    """describe a repo and list its collections.

    use this to discover what collections exist in a repo before listing records.

    examples:
    - describe_repo("zzstoatzz.io") - see what collections a user has
    - describe_repo("did:plc:...") - describe by DID

    args:
        repo: handle or DID to describe

    returns:
        dict with handle, did, collections, and handleIsCorrect
    """
    async with get_atproto_client(
        require_auth=False,
        target_repo=repo,
    ) as client:
        response = await _describe_repo(client, repo)
        return RepoDescriptionResponse(
            handle=response.handle,
            did=response.did,
            collections=response.collections or [],
            handleIsCorrect=response.handle_is_correct,
        )


@mcp.tool
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
    repo_to_use = repo or await get_repo_from_context()
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
async def query(
    nsid: str,
    params: dict[str, Any] | None = None,
    host: str | None = None,
    repo: str | None = None,
    authenticated: bool = False,
) -> dict[str, Any]:
    """call a read-only XRPC *query* method (HTTP GET).

    this is the read counterpart the record tools don't cover — sync, identity,
    server, and the app.bsky.* getter family. it is GET-only and structurally
    cannot create, update, delete, post, or act as a procedure. by default it
    is unauthenticated; pass ``authenticated=True`` for endpoints that require
    a session (e.g., notifications, private feeds, auth-required graph getters).

    examples (unauth):
    - query("com.atproto.sync.listRepos", host="pds.zat.dev")
        -> who is hosted on a PDS
    - query("com.atproto.identity.resolveHandle", params={"handle": "bufo.uk"})
        -> resolve a handle to a DID
    - query("app.bsky.actor.getProfile", params={"actor": "phi.zzstoatzz.io"})
        -> a user's public profile
    - query("app.bsky.feed.getQuotes", params={"uri": "at://.../post/xyz"})
        -> who quoted a post (no auth required)

    examples (auth):
    - query("app.bsky.notification.listNotifications",
            params={"limit": 30}, authenticated=True)
        -> your own notifications

    targeting (choose at most one):
        repo: a handle or DID — routes to that user's PDS (for sync.*/repo.* host queries)
        host: an explicit service base URL or bare host, e.g. "pds.zat.dev"
        neither: defaults to the public appview (unauth) or your PDS (auth);
            your PDS proxies authenticated app.bsky.* calls to the AppView.

    args:
        nsid: the query method, e.g. "com.atproto.sync.listRepos"
        params: query parameters for the method
        host: service to target (bare host gets https://)
        repo: handle or DID whose PDS to target
        authenticated: send the caller's session token (Bearer JWT). still
            GET-only / SSRF-guarded / no-redirects — only the authority axis
            changes, and only NSIDs in ``AUTHENTICATED_QUERY_ALLOWLIST`` are
            permitted (currently notifications). extending the allowlist is
            a deliberate, per-NSID decision: file an issue to add one.

    returns:
        the method's JSON response (large list fields are trimmed; paginate
        with cursor). transport / HTTP / decode failures come back as a
        structured ``{"error": ..., "message": ...}`` dict rather than
        raising — so a bad host guess doesn't burn the caller's retry budget.
    """
    if repo and host:
        raise ValueError("pass either 'repo' or 'host', not both")

    auth_token: str | None = None

    if authenticated:
        # gate at the authority boundary: authenticated reads can expose
        # private account data, so the NSID must be on the explicit allowlist.
        # the unauth path stays open to any NSID (public data anyway).
        if nsid not in AUTHENTICATED_QUERY_ALLOWLIST:
            raise ValueError(
                f"{nsid!r} is not on the authenticated-query allowlist. "
                f"allowed: {sorted(AUTHENTICATED_QUERY_ALLOWLIST)}. file an "
                "issue at https://github.com/zzstoatzz/pdsx if you need it "
                "added — extending the allowlist is a deliberate decision "
                "that the response is acceptable for an agentic caller to "
                "read with the operator's session."
            )
        # resolve the caller's session and extract the access JWT; the JWT is
        # an opaque string we then send as Bearer on the GET. the context
        # manager just yields the client — exiting it does not invalidate the
        # JWT, so it's safe to use after.
        async with get_atproto_client(
            require_auth=True,
            operation="an authenticated query",
        ) as client:
            session = client.me
            access_jwt = (
                getattr(session, "access_jwt", None) if session is not None else None
            )
            if not access_jwt:
                raise AuthenticationRequired("an authenticated query")
            auth_token = access_jwt

    if repo:
        base_url = await discover_pds(repo)
    elif host:
        base_url = normalize_service_url(host)
    elif authenticated:
        # default to the caller's PDS — it proxies authenticated app.bsky.*
        # calls to the AppView, so this works for notifications, private
        # feeds, etc., without the caller needing to know AppView routing.
        base_url = await resolve_pds_url()
    else:
        base_url = PUBLIC_APPVIEW

    try:
        result = await _query(nsid, base_url, params, auth_token=auth_token)
    except httpx.HTTPStatusError as exc:
        # 4xx/5xx — return as data so the model can adapt (wrong host, bad
        # params, etc.) instead of burning the agent's retry budget.
        return {
            "error": "http_status",
            "status": exc.response.status_code,
            "url": str(exc.request.url),
            "message": exc.response.text[:500],
        }
    except httpx.RequestError as exc:
        # DNS/connect/timeout — same reasoning: surface the failure as data.
        return {
            "error": "transport",
            "url": str(exc.request.url) if exc.request else "",
            "message": f"{type(exc).__name__}: {exc}",
        }
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # the endpoint returned non-JSON (e.g. com.atproto.sync.getBlob returns
        # raw blob bytes). `query` is JSON-only by contract — tell the caller
        # they reached for the wrong tool rather than crashing.
        return {
            "error": "non_json_response",
            "message": (
                f"{nsid!r} did not return JSON ({type(exc).__name__}). "
                "this endpoint likely returns binary or non-JSON content — "
                "use a method-specific tool instead of `query`."
            ),
        }
    return _truncate_query_response(result)


@mcp.tool
async def create_record(
    collection: str,
    record: dict[str, Any],
    rkey: str | None = None,
) -> CreateResponse:
    """create a new record. requires authentication.

    args:
        collection: the collection to create in (e.g., 'app.bsky.feed.post')
        record: the record data. $type and createdAt are auto-added if missing.
        rkey: optional record key (e.g., 'self' for profile records, or any fixed key
              required by the lexicon). auto-generated if not provided.

    returns:
        dict with uri and cid of created record
    """
    async with get_atproto_client(
        require_auth=True,
        operation="creating a record",
    ) as client:
        response = await _create_record(client, collection, record, rkey=rkey)
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


@mcp.tool
async def whoami() -> IdentityResponse:
    """get the authenticated user's identity.

    returns the handle and DID of the currently authenticated user.
    requires authentication via x-atproto-handle and x-atproto-password headers.

    returns:
        dict with handle and did of authenticated user
    """
    async with get_atproto_client(
        require_auth=True,
        operation="checking identity",
    ) as client:
        if not client.me:
            raise ValueError("authenticated but no user info available")
        return IdentityResponse(handle=client.me.handle, did=client.me.did)


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
