"""tests for cli module."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pdsx._internal.resolution import discover_pds


def test_whoami_in_help() -> None:
    """test whoami command appears in help."""
    result = subprocess.run(
        ["pdsx", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "whoami" in result.stdout
    assert "me" in result.stdout
    assert "identity" in result.stdout


class TestDescribe:
    """tests for describe (ls without collection) command."""

    async def test_cmd_describe_displays_repo(self) -> None:
        """cmd_describe shows repo info when collection omitted."""
        from pdsx.cli import cmd_describe

        mock_client = MagicMock()

        mock_response = MagicMock()
        mock_response.handle = "test.bsky.social"
        mock_response.did = "did:plc:test123"
        mock_response.handle_is_correct = True
        mock_response.collections = [
            "app.bsky.feed.post",
            "app.bsky.actor.profile",
        ]

        with patch(
            "pdsx.cli.describe_repo", new_callable=AsyncMock, return_value=mock_response
        ):
            await cmd_describe(mock_client, "test.bsky.social")

    async def test_cmd_describe_json_output(self, capsys) -> None:
        """cmd_describe outputs json when requested."""
        from pdsx._internal.output import OutputFormat
        from pdsx.cli import cmd_describe

        mock_client = MagicMock()

        mock_response = MagicMock()
        mock_response.handle = "test.bsky.social"
        mock_response.did = "did:plc:test123"
        mock_response.handle_is_correct = True
        mock_response.collections = ["app.bsky.feed.post"]

        with patch(
            "pdsx.cli.describe_repo", new_callable=AsyncMock, return_value=mock_response
        ):
            await cmd_describe(
                mock_client, "test.bsky.social", output_format=OutputFormat.JSON
            )

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["handle"] == "test.bsky.social"
        assert output["collections"] == ["app.bsky.feed.post"]


class TestWhoami:
    """tests for whoami command."""

    async def test_cmd_whoami_displays_identity(self) -> None:
        """whoami shows handle and DID when authenticated."""
        from pdsx.cli import cmd_whoami

        mock_client = MagicMock()
        mock_client.me = MagicMock()
        mock_client.me.handle = "test.bsky.social"
        mock_client.me.did = "did:plc:test123"

        # should not raise
        await cmd_whoami(mock_client)

    async def test_cmd_whoami_handles_no_auth(self) -> None:
        """whoami handles unauthenticated client."""
        from pdsx.cli import cmd_whoami

        mock_client = MagicMock()
        mock_client.me = None

        # should not raise, just print error
        await cmd_whoami(mock_client)


def test_version_flag_long() -> None:
    """test --version flag displays version."""
    result = subprocess.run(
        ["pdsx", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    output = result.stdout.strip()
    assert output.startswith("pdsx ")
    # ensure we're not showing the hardcoded fallback version
    assert output != "pdsx 0.0.0"


def test_version_flag_short() -> None:
    """test -v flag displays version."""
    result = subprocess.run(
        ["pdsx", "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    output = result.stdout.strip()
    assert output.startswith("pdsx ")


class TestDiscoverPds:
    """tests for discover_pds function."""

    @pytest.mark.parametrize(
        "repo,expected_pds",
        [
            ("zzstoatzz.io", "https://pds.zzstoatzz.io"),
            ("did:plc:xbtmt2zjwlrfegqvch7fboei", "https://pds.zzstoatzz.io"),
        ],
    )
    async def test_discover_pds_from_handle_and_did(
        self, repo: str, expected_pds: str, mocker
    ) -> None:
        """test PDS discovery from both handle and DID."""
        # mock the resolver
        mock_resolver = MagicMock()
        mock_resolver.handle.resolve = AsyncMock(
            return_value="did:plc:xbtmt2zjwlrfegqvch7fboei"
        )

        mock_atproto_data = MagicMock()
        mock_atproto_data.pds = expected_pds
        mock_resolver.did.resolve_atproto_data = AsyncMock(
            return_value=mock_atproto_data
        )

        mocker.patch(
            "pdsx._internal.resolution.AsyncIdResolver", return_value=mock_resolver
        )

        result = await discover_pds(repo)
        assert result == expected_pds

    async def test_discover_pds_handle_resolution_fails(self, mocker) -> None:
        """test that invalid handle raises error."""
        mock_resolver = MagicMock()
        mock_resolver.handle.resolve = AsyncMock(return_value=None)

        mocker.patch(
            "pdsx._internal.resolution.AsyncIdResolver", return_value=mock_resolver
        )

        with pytest.raises(ValueError, match="could not resolve handle"):
            await discover_pds("invalid.handle")

    async def test_discover_pds_no_pds_found(self, mocker) -> None:
        """test that DID without PDS raises error."""
        mock_resolver = MagicMock()
        mock_resolver.handle.resolve = AsyncMock(return_value="did:plc:test123")

        mock_atproto_data = MagicMock()
        mock_atproto_data.pds = None
        mock_resolver.did.resolve_atproto_data = AsyncMock(
            return_value=mock_atproto_data
        )

        mocker.patch(
            "pdsx._internal.resolution.AsyncIdResolver", return_value=mock_resolver
        )

        with pytest.raises(ValueError, match="could not find PDS"):
            await discover_pds("test.handle")


class TestAuthenticatedPdsResolution:
    """writes must target the account's own PDS, not the bsky.social default.

    regression: a bare AsyncClient() defaults to bsky.social, so writes for
    self-hosted accounts were signed by the wrong host and rejected with
    BadJwtSignature.
    """

    @pytest.mark.asyncio
    async def test_write_discovers_pds_from_handle(self, mocker) -> None:
        from pdsx import cli

        mocker.patch.object(cli.settings, "atproto_handle", "zzstoatzz.io")
        mocker.patch.object(cli.settings, "atproto_password", "pw")
        mocker.patch.object(cli.settings, "atproto_pds_url", "https://bsky.social")
        mocker.patch.object(type(cli.settings), "model_fields_set", set())

        discover = mocker.patch.object(
            cli, "discover_pds", AsyncMock(return_value="https://pds.zzstoatzz.io")
        )
        client_cls = mocker.patch.object(cli, "AsyncClient")
        mocker.patch.object(cli, "login", AsyncMock())
        mocker.patch.object(cli, "cmd_delete", AsyncMock())
        mocker.patch.object(
            sys, "argv", ["pdsx", "rm", "site.standard.document/some-rkey"]
        )

        assert await cli.async_main() == 0
        discover.assert_awaited_once_with("zzstoatzz.io")
        assert client_cls.call_args.kwargs["base_url"] == "https://pds.zzstoatzz.io"

    @pytest.mark.asyncio
    async def test_explicit_pds_flag_skips_discovery(self, mocker) -> None:
        from pdsx import cli

        mocker.patch.object(cli.settings, "atproto_handle", "zzstoatzz.io")
        mocker.patch.object(cli.settings, "atproto_password", "pw")

        discover = mocker.patch.object(cli, "discover_pds", AsyncMock())
        client_cls = mocker.patch.object(cli, "AsyncClient")
        mocker.patch.object(cli, "login", AsyncMock())
        mocker.patch.object(cli, "cmd_delete", AsyncMock())
        mocker.patch.object(
            sys,
            "argv",
            ["pdsx", "--pds", "https://other.example", "rm", "a.b.c/rkey"],
        )

        assert await cli.async_main() == 0
        discover.assert_not_awaited()
        assert client_cls.call_args.kwargs["base_url"] == "https://other.example"
