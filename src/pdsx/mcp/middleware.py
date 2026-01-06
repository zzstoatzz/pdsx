"""middleware for pdsx MCP server."""

import logging
from collections.abc import Sequence
from typing import Any

import mcp.types as mt
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from mcp.server.lowlevel.helper_types import ReadResourceContents

logger = logging.getLogger(__name__)


class AtprotoAuthMiddleware(Middleware):
    """extract atproto credentials from http headers with fallback to environment.

    enables multi-tenant deployments where each request can carry
    its own credentials via custom http headers. if headers are not
    present (e.g., in stdio transport), falls back to environment vars.

    headers expected:
        - x-atproto-handle: atproto handle
        - x-atproto-password: atproto app password
        - x-atproto-pds-url: (optional) custom PDS URL
        - x-atproto-repo: (optional) repo to read from (for unauthenticated reads)

    the extracted credentials are stored in the fastmcp context state and can be
    accessed using `get_atproto_client()` from the client module.
    """

    def _extract_credentials(self) -> None:
        """extract credentials from http headers into fastmcp context."""
        from fastmcp.server.dependencies import get_context

        try:
            fastmcp_ctx = get_context()
        except RuntimeError:
            return

        if not fastmcp_ctx:
            return

        headers = get_http_headers(include_all=True)

        handle = headers.get("x-atproto-handle")
        password = headers.get("x-atproto-password")
        pds_url = headers.get("x-atproto-pds-url")
        repo = headers.get("x-atproto-repo")

        if handle:
            logger.debug("extracted atproto handle from http headers")
            fastmcp_ctx.set_state("atproto_handle", handle)

        if password:
            logger.debug("extracted atproto password from http headers")
            fastmcp_ctx.set_state("atproto_password", password)

        if pds_url:
            logger.debug("extracted atproto pds url from http headers")
            fastmcp_ctx.set_state("atproto_pds_url", pds_url)

        if repo:
            logger.debug("extracted atproto repo from http headers")
            fastmcp_ctx.set_state("atproto_repo", repo)

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, Any],
    ) -> Any:
        """extract credentials from headers on each tool call."""
        self._extract_credentials()
        return await call_next(context)

    async def on_read_resource(
        self,
        context: MiddlewareContext[mt.ReadResourceRequestParams],
        call_next: CallNext[
            mt.ReadResourceRequestParams, Sequence[ReadResourceContents]
        ],
    ) -> Sequence[ReadResourceContents]:
        """extract credentials from headers on each resource read."""
        self._extract_credentials()
        return await call_next(context)
