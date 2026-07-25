"""tests for authentication."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from atproto.exceptions import AtProtocolError

from pdsx._internal.auth import login_with_session_fallback


def _session(did: str = "did:plc:test", handle: str = "zat.dev") -> MagicMock:
    return MagicMock(did=did, handle=handle)


class TestLoginWithoutAppviewProxy:
    """a PDS that doesn't proxy app.bsky.actor.getProfile must still log in.

    regression: AsyncClient.login sets the session and *then* fetches the
    profile from the AppView. On a PDS that doesn't proxy that method (zds
    404s with UnknownMethod), the second step failed and took the whole login
    with it, breaking every authenticated command against such a host.
    """

    async def test_profile_failure_falls_back_to_session_identity(self) -> None:
        client = MagicMock()
        client.login = AsyncMock(side_effect=AtProtocolError("UnknownMethod"))
        client._session = _session()
        client.me = None

        await login_with_session_fallback(client, "zat.dev", "pw")

        assert client.me.did == "did:plc:test"
        assert client.me.handle == "zat.dev"

    async def test_no_session_still_raises(self) -> None:
        """createSession itself failing (bad password) must not be swallowed."""
        client = MagicMock()
        client.login = AsyncMock(side_effect=AtProtocolError("InvalidLogin"))
        client._session = None

        with pytest.raises(AtProtocolError):
            await login_with_session_fallback(client, "zat.dev", "wrong")

    async def test_normal_login_untouched(self) -> None:
        """on a PDS that proxies the AppView, nothing changes."""
        client = MagicMock()
        client.login = AsyncMock()
        client.me = "profile-from-appview"

        await login_with_session_fallback(client, "zzstoatzz.io", "pw")

        client.login.assert_awaited_once_with("zzstoatzz.io", "pw")
        assert client.me == "profile-from-appview"
