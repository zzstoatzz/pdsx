"""experimental permissioned-data helpers (`com.atproto.space.*`).

The permissioned-data proposal is still moving and most PDS implementations do
not serve the namespace at all. Everything here is built to degrade cleanly on
those hosts rather than surface a raw HTTP error, so callers can offer the
commands unconditionally.

Detection is necessarily authenticated: PDS implementations run auth middleware
before method dispatch, so an anonymous probe returns 401 on a host that
supports permissioned data and 401 on one that does not. The distinguishing
signal only appears once a request carries credentials.

Proposal: https://github.com/bluesky-social/proposals/tree/main/0016-permissioned-data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from pdsx._internal.operations import query

if TYPE_CHECKING:
    from atproto import AsyncClient

LIST_SPACES = "com.atproto.space.listSpaces"
LIST_RECORDS = "com.atproto.space.listRecords"
GET_RECORD = "com.atproto.space.getRecord"

# a host that never implemented the namespace and one that implements it behind
# a disabled operator flag both answer this way; the wire gives us no way to
# tell them apart, so callers must not claim to know which it is
_UNSUPPORTED_ERRORS = ("MethodNotImplemented", "XRPCNotSupported")


class PermissionedDataUnsupported(Exception):
    """the target PDS does not serve `com.atproto.space.*`.

    Either the implementation lacks permissioned data entirely or an operator
    has disabled it. Both are reported the same way upstream.
    """


class NotAuthenticated(Exception):
    """permissioned-data reads require an authenticated session."""


def access_jwt(client: AsyncClient) -> str:
    """pull the session JWT off an authenticated client.

    The token lives on ``client._session``; ``client.me`` is a profile view and
    has no ``access_jwt``, so reading it from there fails *after* a successful
    login and looks like missing credentials.
    """
    session = getattr(client, "_session", None)
    token = getattr(session, "access_jwt", None) if session is not None else None
    if not token:
        raise NotAuthenticated("permissioned-data reads require authentication")
    return token


def _is_unsupported(exc: httpx.HTTPStatusError) -> bool:
    """does this response mean "this PDS doesn't do permissioned data"?"""
    status = exc.response.status_code
    if status == 501:
        return True
    # some hosts answer unknown XRPC methods with 404 + an atproto error body;
    # a bare 404 is not enough, since it's also how a real method reports a
    # missing space or record
    if status == 404:
        return any(name in exc.response.text for name in _UNSUPPORTED_ERRORS)
    return False


async def space_query(
    client: AsyncClient,
    nsid: str,
    pds_url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """issue an authenticated permissioned-data query.

    Raises:
        NotAuthenticated: if the client has no session
        PermissionedDataUnsupported: if the PDS does not serve the namespace
    """
    token = access_jwt(client)
    try:
        return await query(nsid, pds_url, params or {}, auth_token=token)
    except httpx.HTTPStatusError as exc:
        if _is_unsupported(exc):
            raise PermissionedDataUnsupported(
                f"{pds_url} does not serve permissioned data "
                f"(it may be unimplemented, or disabled by the operator)"
            ) from exc
        raise


async def supports_permissioned_data(client: AsyncClient, pds_url: str) -> bool:
    """probe whether a PDS serves the permissioned-data namespace.

    Uses listSpaces, which is read-only and scoped to the authenticated actor.
    """
    try:
        await space_query(client, LIST_SPACES, pds_url, {"limit": 1})
    except PermissionedDataUnsupported:
        return False
    return True


async def list_spaces(
    client: AsyncClient,
    pds_url: str,
    *,
    did: str | None = None,
    space_type: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    """list spaces the authenticated actor owns or holds a writer repo in.

    Being named in a space's member list does not put it here — that is
    management policy state, not actor-local space state.
    """
    params: dict[str, Any] = {"limit": limit}
    if did:
        params["did"] = did
    if space_type:
        params["type"] = space_type
    if cursor:
        params["cursor"] = cursor
    return await space_query(client, LIST_SPACES, pds_url, params)


async def list_space_records(
    client: AsyncClient,
    pds_url: str,
    *,
    space: str,
    repo: str,
    collection: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    exclude_values: bool = False,
) -> dict[str, Any]:
    """list records in a permissioned space.

    Values are returned by default, per the proposal; pass exclude_values to
    get just collection/rkey/cid without materializing record JSON.
    """
    params: dict[str, Any] = {"space": space, "repo": repo, "limit": limit}
    if collection:
        params["collection"] = collection
    if cursor:
        params["cursor"] = cursor
    if exclude_values:
        params["excludeValues"] = True
    return await space_query(client, LIST_RECORDS, pds_url, params)


async def get_space_record(
    client: AsyncClient,
    pds_url: str,
    *,
    space: str,
    repo: str,
    collection: str,
    rkey: str,
) -> dict[str, Any]:
    """get a single record from a permissioned space."""
    return await space_query(
        client,
        GET_RECORD,
        pds_url,
        {"space": space, "repo": repo, "collection": collection, "rkey": rkey},
    )
