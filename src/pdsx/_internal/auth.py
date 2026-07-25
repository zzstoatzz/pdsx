"""authentication utilities for atproto."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from atproto import models
from atproto.exceptions import AtProtocolError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

if TYPE_CHECKING:
    from atproto import AsyncClient

console = Console()

# silence httpx logs
logging.getLogger("httpx").setLevel(logging.CRITICAL)


async def _login(client: AsyncClient, handle: str, password: str) -> None:
    """log in, tolerating PDSes that do not proxy AppView methods.

    ``AsyncClient.login`` establishes the session and then populates
    ``client.me`` via ``app.bsky.actor.getProfile`` — an AppView method. A PDS
    that doesn't proxy it (zds, for one) answers 404 ``UnknownMethod`` at that
    second step, *after* the session is already set, so a login that actually
    succeeded surfaces as a total failure.

    Only the profile lookup is optional, so fall back to the identity the
    session already carries. A non-existent session means createSession itself
    failed (bad credentials), which must still raise.
    """
    try:
        await client.login(handle, password)
    except AtProtocolError:
        session = getattr(client, "_session", None)
        if session is None:
            raise
        client.me = models.AppBskyActorDefs.ProfileViewDetailed(
            did=session.did, handle=session.handle
        )


async def login(
    client: AsyncClient,
    handle: str | None = None,
    password: str | None = None,
    *,
    silent: bool = False,
    required: bool = True,
) -> bool:
    """authenticate with atproto.

    Args:
        client: atproto client to authenticate
        handle: user handle
        password: user password
        silent: suppress authentication output
        required: whether authentication is required

    Returns:
        True if authenticated, False if skipped (when not required)
    """
    if not handle or not password:
        if required:
            console.print(
                "[red]error:[/red] provide --handle/--password or set ATPROTO_HANDLE/ATPROTO_PASSWORD"
            )
            sys.exit(1)
        return False

    if not silent:
        with Progress(
            SpinnerColumn(),
            TextColumn("[dim]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("authenticating...", total=None)
            await _login(client, handle, password)
        console.print(f"[dim]✓ authenticated as[/dim] {handle}\n")
    else:
        await _login(client, handle, password)

    return True
