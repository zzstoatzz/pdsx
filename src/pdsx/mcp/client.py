"""helper for creating atproto clients with per-request credentials."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from atproto import AsyncClient

from pdsx.mcp._types import CredentialsContext

logger = logging.getLogger(__name__)


def _get_credentials_from_context() -> CredentialsContext:
    """extract credentials from fastmcp context if available.

    returns:
        credentials dict with handle, password, pds_url, repo (any may be None)
    """
    result: CredentialsContext = {
        "handle": None,
        "password": None,
        "pds_url": None,
        "repo": None,
    }

    try:
        from fastmcp.server.dependencies import get_context

        ctx = get_context()
        result["handle"] = ctx.get_state("atproto_handle")
        result["password"] = ctx.get_state("atproto_password")
        result["pds_url"] = ctx.get_state("atproto_pds_url")
        result["repo"] = ctx.get_state("atproto_repo")
    except RuntimeError as e:
        if "No active context found" not in str(e):
            raise
    except AttributeError as e:
        if "get_state" not in str(e):
            raise

    return result


AUTH_HELP = """\
authentication required but no credentials provided.

to authenticate, set headers when configuring the MCP server:
  - x-atproto-handle: your atproto handle (e.g., 'you.bsky.social')
  - x-atproto-password: your atproto app password

example claude code configuration:
  claude mcp add-json pdsx '{
    "type": "http",
    "url": "https://pdsx-by-zzstoatzz.fastmcp.app/mcp",
    "headers": {
      "x-atproto-handle": "your.handle",
      "x-atproto-password": "your-app-password"
    }
  }'

for local/stdio usage, set environment variables instead:
  export ATPROTO_HANDLE=your.handle
  export ATPROTO_PASSWORD=your-app-password

see https://pdsx.zzstoatzz.io for full documentation."""


class AuthenticationRequired(Exception):
    """raised when an operation requires authentication but none was provided."""

    def __init__(self, operation: str = "this operation"):
        super().__init__(f"{operation} requires authentication.\n\n{AUTH_HELP}")


@asynccontextmanager
async def get_atproto_client(
    require_auth: bool = False,
    operation: str = "this operation",
    target_repo: str | None = None,
) -> AsyncIterator[AsyncClient]:
    """get an atproto client using credentials from context or environment.

    first checks if credentials were provided via http headers (stored in fastmcp
    context state by AtprotoAuthMiddleware). if found, creates an authenticated
    client. otherwise falls back to ATPROTO_HANDLE/ATPROTO_PASSWORD environment
    variables.

    when target_repo is provided and no auth is required, automatically discovers
    and uses the correct PDS for that user (handles users on self-hosted PDS).

    this enables both:
    - multi-tenant http deployments (credentials per request via headers)
    - traditional stdio deployments (credentials from environment)

    args:
        require_auth: if True, raises AuthenticationRequired when no credentials
        operation: description of the operation for error messages
        target_repo: handle or DID to read from (triggers PDS discovery when set)

    yields:
        a configured async atproto client

    raises:
        AuthenticationRequired: if require_auth=True and no credentials available

    example:
        async with get_atproto_client() as client:
            records = await client.com.atproto.repo.list_records(...)
    """
    creds = _get_credentials_from_context()

    # use context credentials if available, else fall back to env
    handle = creds["handle"] or os.environ.get("ATPROTO_HANDLE", "")
    password = creds["password"] or os.environ.get("ATPROTO_PASSWORD", "")

    # determine PDS URL:
    # 1. if target_repo provided and not requiring auth, discover their PDS
    # 2. otherwise use configured PDS or default to bsky.social
    pds_url: str | None = None
    skip_auth = False

    if target_repo and not require_auth:
        # discover PDS for the target repo
        from pdsx._internal.resolution import discover_pds

        try:
            pds_url = await discover_pds(target_repo)
            logger.debug("discovered PDS for %s: %s", target_repo, pds_url)
            # don't authenticate when reading from another user's PDS
            # (our credentials won't work on their PDS)
            skip_auth = True
        except ValueError as e:
            logger.warning("failed to discover PDS for %s: %s", target_repo, e)

    if not pds_url:
        pds_url = (
            creds["pds_url"]
            or os.environ.get("ATPROTO_PDS_URL")
            or "https://bsky.social"
        )

    client = AsyncClient(pds_url)

    if require_auth:
        if handle and password:
            logger.debug("authenticating with provided credentials")
            await client.login(handle, password)
        else:
            raise AuthenticationRequired(operation)
    elif handle and password and not skip_auth:
        # only authenticate if we're not reading from another user's PDS
        logger.debug("authenticating with provided credentials")
        await client.login(handle, password)
    else:
        logger.debug("using unauthenticated client for %s", pds_url)

    try:
        yield client
    finally:
        pass  # AsyncClient doesn't need explicit cleanup


def get_repo_from_context() -> str | None:
    """get repo override from context if set via x-atproto-repo header."""
    creds = _get_credentials_from_context()
    repo = creds.get("repo")
    if not repo:
        repo = os.environ.get("ATPROTO_REPO")
    return repo
