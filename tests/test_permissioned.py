"""tests for experimental permissioned-data helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pdsx._internal.permissioned import (
    NotAuthenticated,
    PermissionedDataUnsupported,
    SpaceQueryError,
    access_jwt,
    get_space_record,
    list_spaces,
    space_query,
    supports_permissioned_data,
)

PDS = "https://pds.example"


def _client(token: str | None = "jwt-token") -> MagicMock:
    client = MagicMock()
    client._session = MagicMock(access_jwt=token) if token else None
    return client


def _http_error(status: int, body: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"{PDS}/xrpc/com.atproto.space.listSpaces")
    response = httpx.Response(status, text=body, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class TestAccessJwt:
    def test_reads_session_not_me(self) -> None:
        """the token lives on _session; client.me is a profile view."""
        client = _client("abc")
        client.me = MagicMock(spec=[])  # no access_jwt attribute
        assert access_jwt(client) == "abc"

    def test_missing_session_raises(self) -> None:
        with pytest.raises(NotAuthenticated):
            access_jwt(_client(None))


class TestUnsupportedDetection:
    """a PDS that doesn't serve com.atproto.space.* must degrade, not explode."""

    async def test_501_is_unsupported(self, mocker) -> None:
        """the documented signal: zds returns this when the flag is off."""
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(
                side_effect=_http_error(
                    501,
                    '{"error":"MethodNotImplemented","message":"Method Not Implemented"}',
                )
            ),
        )
        with pytest.raises(PermissionedDataUnsupported):
            await space_query(_client(), "com.atproto.space.listSpaces", PDS)

    async def test_404_xrpc_not_supported_is_unsupported(self, mocker) -> None:
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(side_effect=_http_error(404, '{"error":"XRPCNotSupported"}')),
        )
        with pytest.raises(PermissionedDataUnsupported):
            await space_query(_client(), "com.atproto.space.listSpaces", PDS)

    async def test_404_record_not_found_propagates(self, mocker) -> None:
        """a missing record on a supporting PDS is NOT a capability failure.

        Treating every 404 as "unsupported" would report a real, working
        permissioned-data host as incapable the moment a record was missing.
        """
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(
                side_effect=_http_error(
                    404, '{"error":"RecordNotFound","message":"Record not found"}'
                )
            ),
        )
        with pytest.raises(SpaceQueryError, match="RecordNotFound"):
            await get_space_record(
                _client(),
                PDS,
                space="at://did:plc:a/space/com.example.t/s",
                repo="did:plc:a",
                collection="com.example.c",
                rkey="r",
            )

    async def test_other_errors_propagate(self, mocker) -> None:
        """auth failures must not be laundered into 'unsupported'."""
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(side_effect=_http_error(401, '{"error":"AuthMissing"}')),
        )
        with pytest.raises(SpaceQueryError, match="AuthMissing"):
            await space_query(_client(), "com.atproto.space.listSpaces", PDS)


class TestSupportsProbe:
    async def test_false_when_unimplemented(self, mocker) -> None:
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(side_effect=_http_error(501, '{"error":"MethodNotImplemented"}')),
        )
        assert await supports_permissioned_data(_client(), PDS) is False

    async def test_true_when_served(self, mocker) -> None:
        mocker.patch(
            "pdsx._internal.permissioned.query",
            AsyncMock(return_value={"spaces": []}),
        )
        assert await supports_permissioned_data(_client(), PDS) is True


class TestListSpacesParams:
    async def test_optional_params_omitted(self, mocker) -> None:
        q = mocker.patch(
            "pdsx._internal.permissioned.query", AsyncMock(return_value={"spaces": []})
        )
        await list_spaces(_client(), PDS)
        assert q.await_args.args[2] == {"limit": 50}

    async def test_filters_passed_through(self, mocker) -> None:
        q = mocker.patch(
            "pdsx._internal.permissioned.query", AsyncMock(return_value={"spaces": []})
        )
        await list_spaces(
            _client(), PDS, did="did:plc:a", space_type="com.example.t", cursor="c"
        )
        assert q.await_args.args[2] == {
            "limit": 50,
            "did": "did:plc:a",
            "type": "com.example.t",
            "cursor": "c",
        }


class TestCommandDegradation:
    """enumeration degrades to an explicit empty result; targeted reads fail."""

    async def test_ls_exits_zero_and_reports_unsupported(self, mocker, capsys) -> None:
        from pdsx import cli
        from pdsx._internal.output import OutputFormat

        mocker.patch.object(
            cli,
            "list_spaces",
            AsyncMock(side_effect=PermissionedDataUnsupported("nope")),
        )
        code = await cli.cmd_spaces_list(
            _client(), PDS, output_format=OutputFormat.JSON
        )
        assert code == 0
        assert '"supported": false' in capsys.readouterr().out

    async def test_get_exits_nonzero_when_unsupported(self, mocker) -> None:
        from pdsx import cli

        mocker.patch.object(
            cli,
            "get_space_record",
            AsyncMock(side_effect=PermissionedDataUnsupported("nope")),
        )
        code = await cli.cmd_space_get(
            _client(),
            PDS,
            space="at://did:plc:a/space/com.example.t/s",
            repo="did:plc:a",
            collection="com.example.c",
            rkey="r",
        )
        assert code == 1
