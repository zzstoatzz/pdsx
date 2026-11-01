"""account lifecycle tools, registered only when PDSX_ENABLE_ACCOUNT_TOOLS=1.

these exist for sandboxed evals against a disposable PDS. once
``create_account`` succeeds, the new account becomes the active credentials for
every later tool call in this process, so ``create_record`` and friends act as
it. the hosted server never sets the flag, so none of this is reachable there.
"""

import os
from typing import Any

from atproto import AsyncClient, models
from fastmcp import FastMCP

from pdsx.mcp.client import (
    AuthenticationRequired,
    clear_active_account,
    get_active_account,
    get_atproto_client,
    resolve_pds_url,
    set_active_account,
)

ENABLE_FLAG = "PDSX_ENABLE_ACCOUNT_TOOLS"


def account_tools_enabled() -> bool:
    return os.environ.get(ENABLE_FLAG) == "1"


async def create_account(
    handle: str,
    email: str,
    password: str,
    pds: str | None = None,
    invite_code: str | None = None,
) -> dict[str, Any]:
    """create an account on a PDS and switch this session to it.

    after this succeeds, record tools (create_record, delete_record, whoami, ...)
    act as the new account.

    args:
        handle: full handle, within one of the PDS's service handle domains
        email: account email; deletion confirmations are sent here
        password: account password
        pds: PDS URL (defaults to the configured PDS)
        invite_code: only if the PDS requires invites

    returns:
        dict with did, handle and pds of the new account
    """
    pds_url = pds or await resolve_pds_url()
    client = AsyncClient(pds_url)
    response = await client.com.atproto.server.create_account(
        models.ComAtprotoServerCreateAccount.Data(
            handle=handle, email=email, password=password, invite_code=invite_code
        )
    )
    set_active_account(
        handle=response.handle, did=response.did, password=password, pds_url=pds_url
    )
    return {"did": response.did, "handle": response.handle, "pds": pds_url}


async def request_account_delete() -> dict[str, str]:
    """ask the PDS to email a deletion token to the active account.

    returns:
        confirmation naming the account; pass the emailed token to delete_account
    """
    async with get_atproto_client(
        require_auth=True, operation="requesting account deletion"
    ) as client:
        await client.com.atproto.server.request_account_delete()
        did = client.me.did if client.me else ""
    return {"requested": did, "next": "call delete_account with the emailed token"}


async def delete_account(token: str) -> dict[str, str]:
    """permanently delete the account created in this session.

    args:
        token: the deletion token from the confirmation email

    returns:
        confirmation with the deleted did
    """
    account = get_active_account()
    if account is None:
        raise AuthenticationRequired("deleting an account created in this session")
    client = AsyncClient(account["pds_url"])
    await client.com.atproto.server.delete_account(
        models.ComAtprotoServerDeleteAccount.Data(
            did=account["did"], password=account["password"], token=token.strip()
        )
    )
    clear_active_account()
    return {"deleted": account["did"]}


def register_account_tools(mcp: FastMCP) -> None:
    for tool in (create_account, request_account_delete, delete_account):
        mcp.tool(tool)
