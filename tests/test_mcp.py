"""tests for pdsx MCP server."""

import json

import pytest

from pdsx.mcp._types import (
    CreateResponse,
    CredentialsContext,
    DeleteResponse,
    RecordResponse,
    RepoDescriptionResponse,
    UpdateResponse,
)
from pdsx.mcp.client import AUTH_HELP, AuthenticationRequired
from pdsx.mcp.server import (
    MAX_LIMIT,
    MAX_RESPONSE_CHARS,
    _clean_value,
    _truncate_list_response,
)


class TestAuthenticationRequired:
    """tests for the AuthenticationRequired exception."""

    def test_exception_message(self):
        """exception includes helpful message."""
        exc = AuthenticationRequired("creating a post")
        assert "creating a post requires authentication" in str(exc)
        assert AUTH_HELP in str(exc)

    def test_exception_default_operation(self):
        """exception has default operation name."""
        exc = AuthenticationRequired()
        assert "this operation requires authentication" in str(exc)


class TestTypedDicts:
    """tests for the typed dict definitions."""

    def test_record_response(self):
        """RecordResponse can be constructed."""
        r = RecordResponse(uri="at://...", cid="baf...", value={"text": "hi"})
        assert r["uri"] == "at://..."
        assert r["cid"] == "baf..."
        assert r["value"] == {"text": "hi"}

    def test_create_response(self):
        """CreateResponse can be constructed."""
        r = CreateResponse(uri="at://...", cid="baf...")
        assert r["uri"] == "at://..."
        assert r["cid"] == "baf..."

    def test_update_response(self):
        """UpdateResponse can be constructed."""
        r = UpdateResponse(uri="at://...", cid="baf...")
        assert r["uri"] == "at://..."

    def test_delete_response(self):
        """DeleteResponse can be constructed."""
        r = DeleteResponse(deleted="at://...")
        assert r["deleted"] == "at://..."

    def test_repo_description_response(self):
        """RepoDescriptionResponse can be constructed."""
        r = RepoDescriptionResponse(
            handle="test.bsky.social",
            did="did:plc:test123",
            collections=["app.bsky.feed.post", "app.bsky.actor.profile"],
            handleIsCorrect=True,
        )
        assert r["handle"] == "test.bsky.social"
        assert r["did"] == "did:plc:test123"
        assert r["collections"] == ["app.bsky.feed.post", "app.bsky.actor.profile"]
        assert r["handleIsCorrect"] is True

    def test_credentials_context(self):
        """CredentialsContext can be constructed."""
        c = CredentialsContext(
            handle="test.bsky.social",
            password="secret",
            pds_url="https://bsky.social",
            repo=None,
        )
        assert c["handle"] == "test.bsky.social"
        assert c["password"] == "secret"
        assert c["pds_url"] == "https://bsky.social"
        assert c["repo"] is None


class TestMcpServerImports:
    """tests for MCP server module imports."""

    def test_mcp_server_imports(self):
        """mcp server can be imported without errors."""
        from pdsx.mcp import mcp

        assert mcp.name == "pdsx"

    def test_exports(self):
        """all expected exports are available."""
        from pdsx.mcp import (
            AtprotoAuthMiddleware,
            AuthenticationRequired,
            get_atproto_client,
            mcp,
        )

        assert AtprotoAuthMiddleware is not None
        assert AuthenticationRequired is not None
        assert get_atproto_client is not None
        assert mcp is not None


class TestAtprotoAuthMiddleware:
    """tests for AtprotoAuthMiddleware."""

    def test_middleware_has_on_call_tool(self):
        """middleware implements on_call_tool hook."""
        from pdsx.mcp.middleware import AtprotoAuthMiddleware

        middleware = AtprotoAuthMiddleware()
        # should have custom implementation, not just inherited
        assert hasattr(middleware, "on_call_tool")
        # check it's not the base class implementation
        from fastmcp.server.middleware import Middleware

        assert middleware.on_call_tool.__func__ is not Middleware.on_call_tool

    def test_middleware_has_on_read_resource(self):
        """middleware implements on_read_resource hook for resource auth.

        regression test: without this, the pdsx://me resource can't access
        credentials from http headers because middleware only ran for tools.
        """
        from pdsx.mcp.middleware import AtprotoAuthMiddleware

        middleware = AtprotoAuthMiddleware()
        assert hasattr(middleware, "on_read_resource")
        # check it's not the base class implementation
        from fastmcp.server.middleware import Middleware

        assert middleware.on_read_resource.__func__ is not Middleware.on_read_resource


class TestGetAtprotoClient:
    """tests for get_atproto_client with PDS discovery."""

    async def test_pds_discovery_for_target_repo(self):
        """discovers correct PDS when target_repo is provided."""
        from pdsx.mcp.client import get_atproto_client

        # should discover pds.zzstoatzz.io for this user
        async with get_atproto_client(target_repo="zzstoatzz.io") as client:
            assert "pds.zzstoatzz.io" in client._base_url

    async def test_pds_discovery_standard_user(self):
        """uses bsky network PDS for standard users."""
        from pdsx.mcp.client import get_atproto_client

        async with get_atproto_client(target_repo="jay.bsky.team") as client:
            assert "bsky.network" in client._base_url

    async def test_default_pds_when_no_target(self):
        """uses default bsky.social when no target_repo."""
        from pdsx.mcp.client import get_atproto_client

        async with get_atproto_client() as client:
            assert "bsky.social" in client._base_url

    async def test_skips_auth_when_reading_other_pds(self, monkeypatch):
        """doesn't try to authenticate when reading from another user's PDS."""

        from pdsx.mcp.client import get_atproto_client

        # simulate having credentials configured (like via headers)
        monkeypatch.setenv("ATPROTO_HANDLE", "someone.bsky.social")
        monkeypatch.setenv("ATPROTO_PASSWORD", "fake-password")

        # should discover zzstoatzz.io's PDS and NOT try to login
        # (because our bsky.social credentials won't work on their PDS)
        async with get_atproto_client(target_repo="zzstoatzz.io") as client:
            assert "pds.zzstoatzz.io" in client._base_url
            # client.me is None when not authenticated
            assert client.me is None


class TestCleanValue:
    """tests for _clean_value helper."""

    def test_clean_value_handles_pydantic_models(self):
        """converts Pydantic models to plain dict using model_dump."""
        from pydantic import BaseModel

        class PostRecord(BaseModel):
            text: str
            createdAt: str
            embed: str | None = None
            labels: str | None = None

            model_config = {"populate_by_name": True}

        value = PostRecord(
            text="hello world",
            createdAt="2025-01-01T00:00:00Z",
            embed=None,
            labels=None,
        )

        cleaned = _clean_value(value)

        # should be JSON serializable and cleaned
        json_str = json.dumps(cleaned)
        assert "hello world" in json_str
        # null fields should be removed
        assert "embed" not in cleaned
        assert "labels" not in cleaned

    def test_clean_value_handles_real_atproto_dotdict(self):
        """handles atproto's DotDict which has model_dump=None."""
        from atproto_client.models.dot_dict import DotDict

        # DotDict has model_dump attribute but it's None (not callable)
        value = DotDict(
            {
                "text": "hello from dotdict",
                "$type": "fm.plyr.dev.list",
                "items": [{"uri": "at://...", "name": "test"}],
                "createdAt": "2025-01-01T00:00:00Z",
                "nullField": None,
            }
        )

        # verify DotDict has the problematic model_dump=None
        assert hasattr(value, "model_dump")
        assert value.model_dump is None
        assert not callable(value.model_dump)

        cleaned = _clean_value(value)

        # should be JSON serializable
        json_str = json.dumps(cleaned)
        assert "hello from dotdict" in json_str

        # should have cleaned up
        assert "$type" not in cleaned
        assert "nullField" not in cleaned

    def test_clean_value_handles_nested_dotdict(self):
        """handles nested DotDict structures."""
        from atproto_client.models.dot_dict import DotDict

        value = DotDict(
            {
                "name": "playlist",
                "items": [
                    DotDict({"uri": "at://1", "title": "song1"}),
                    DotDict({"uri": "at://2", "title": "song2"}),
                ],
            }
        )

        cleaned = _clean_value(value)

        # should be JSON serializable
        json_str = json.dumps(cleaned)
        assert "playlist" in json_str
        assert "at://1" in json_str

    def test_clean_value_removes_null_fields(self):
        """null fields are removed from output."""
        value = {"text": "hello", "embed": None, "labels": None}
        cleaned = _clean_value(value)

        assert "text" in cleaned
        assert "embed" not in cleaned
        assert "labels" not in cleaned

    def test_clean_value_removes_type_field(self):
        """$type field is removed from output."""
        value = {"$type": "app.bsky.feed.post", "text": "hello"}
        cleaned = _clean_value(value)

        assert "$type" not in cleaned
        assert cleaned["text"] == "hello"


class TestContextFloodingProtection:
    """tests for context flooding protection in the MCP server."""

    def test_max_limit_constant_exists(self):
        """MAX_LIMIT constant is defined."""
        assert MAX_LIMIT == 25

    def test_max_response_chars_constant_exists(self):
        """MAX_RESPONSE_CHARS constant is defined."""
        assert MAX_RESPONSE_CHARS == 30000

    def test_truncate_response_small_response_unchanged(self):
        """small responses pass through unchanged."""
        records = [
            RecordResponse(uri="at://test/post/1", cid="cid1", value={"text": "hi"}),
            RecordResponse(uri="at://test/post/2", cid="cid2", value={"text": "hello"}),
        ]
        result = _truncate_list_response(records, total_fetched=2, has_more=False)

        # should return the original list unchanged
        assert result == records

    def test_truncate_response_large_response_truncated(self):
        """large responses are truncated with a message."""
        # create records that exceed the limit
        large_text = "x" * 2000  # 2KB per record
        records = [
            RecordResponse(
                uri=f"at://test/post/{i}",
                cid=f"cid{i}",
                value={"text": f"{large_text}_{i}"},
            )
            for i in range(50)  # ~100KB total
        ]
        result = _truncate_list_response(records, total_fetched=50, has_more=True)

        # should be a dict with truncated records
        assert isinstance(result, dict)
        assert "records" in result
        assert "truncated" in result
        assert result["truncated"] is True
        assert "message" in result
        assert "shown" in result
        assert "fetched" in result

        # truncated list should be smaller
        assert len(result["records"]) < 50

        # serialized should be under limit
        serialized = json.dumps(result["records"], default=str)
        assert len(serialized) <= MAX_RESPONSE_CHARS

        # message should mention pagination
        assert "cursor" in result["message"]

    def test_truncate_response_no_more_available(self):
        """truncation message differs when no more records available."""
        large_text = "x" * 2000
        records = [
            RecordResponse(
                uri=f"at://test/post/{i}",
                cid=f"cid{i}",
                value={"text": f"{large_text}_{i}"},
            )
            for i in range(50)
        ]
        result = _truncate_list_response(records, total_fetched=50, has_more=False)

        assert isinstance(result, dict)
        # message should NOT mention cursor when no more available
        assert "more available via cursor" not in result["message"]


class _FakeAsyncContext:
    """fastmcp 3.x-style context whose get_state/set_state are coroutines."""

    def __init__(self, state: dict | None = None):
        self._state: dict = dict(state or {})

    async def get_state(self, key: str):
        return self._state.get(key)

    async def set_state(self, key: str, value, *, serializable: bool = True) -> None:
        self._state[key] = value


class _FakeSyncContext:
    """fastmcp 2.x-style context whose get_state/set_state are plain sync.

    also matches hosted runtimes (e.g. FastMCP Cloud) that may serve a fastmcp
    different from our pinned dependency — the reason the fix must not assume
    either calling convention (see #85).
    """

    def __init__(self, state: dict | None = None):
        self._state: dict = dict(state or {})

    def get_state(self, key: str):
        return self._state.get(key)

    def set_state(self, key: str, value, *, serializable: bool = True) -> None:
        self._state[key] = value


# both context styles must work: 3.x (async) and 2.x / hosted (sync)
_CONTEXT_KINDS = [_FakeAsyncContext, _FakeSyncContext]


class TestAsyncStateRegression:
    """regression tests for #85: fastmcp made Context.get_state / set_state
    coroutines in 3.x but they're plain sync in 2.x, and hosted runtimes may
    pin either. pdsx must handle both — otherwise credentials come back as
    un-awaited coroutines (`'coroutine' object has no attribute 'startswith'`)
    or `await` blows up on a plain return value (`object NoneType can't be used
    in 'await' expression`).
    """

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_get_credentials_resolves_strings(self, monkeypatch, ctx_cls):
        """credentials resolve to plain strings under sync OR async get_state."""
        import fastmcp.server.dependencies as deps

        from pdsx.mcp.client import _get_credentials_from_context

        ctx = ctx_cls(
            {
                "atproto_handle": "alice.bsky.social",
                "atproto_password": "app-pw",
                "atproto_pds_url": "https://pds.example",
                "atproto_repo": "alice.bsky.social",
            }
        )
        monkeypatch.setattr(deps, "get_context", lambda: ctx)

        creds = await _get_credentials_from_context()

        assert creds["handle"] == "alice.bsky.social"
        assert creds["password"] == "app-pw"
        assert creds["pds_url"] == "https://pds.example"
        assert creds["repo"] == "alice.bsky.social"
        # the actual bug: values must be resolved strings, not coroutine objects
        for value in creds.values():
            assert isinstance(value, str)

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_get_repo_from_context(self, monkeypatch, ctx_cls):
        """get_repo_from_context returns the resolved repo string."""
        import fastmcp.server.dependencies as deps

        from pdsx.mcp.client import get_repo_from_context

        ctx = ctx_cls({"atproto_repo": "alice.bsky.social"})
        monkeypatch.setattr(deps, "get_context", lambda: ctx)

        assert await get_repo_from_context() == "alice.bsky.social"

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_resolve_pds_url(self, monkeypatch, ctx_cls):
        """resolve_pds_url returns the header pds_url, not a coroutine."""
        import fastmcp.server.dependencies as deps

        from pdsx.mcp.client import resolve_pds_url

        ctx = ctx_cls({"atproto_pds_url": "https://pds.example"})
        monkeypatch.setattr(deps, "get_context", lambda: ctx)

        assert await resolve_pds_url() == "https://pds.example"

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_middleware_writes_state(self, monkeypatch, ctx_cls):
        """middleware writes header credentials into context state under both
        sync and async set_state."""
        import fastmcp.server.dependencies as deps

        from pdsx.mcp import middleware as mw

        ctx = ctx_cls()
        monkeypatch.setattr(deps, "get_context", lambda: ctx)
        monkeypatch.setattr(
            mw,
            "get_http_headers",
            lambda include_all=True: {
                "x-atproto-handle": "alice.bsky.social",
                "x-atproto-password": "app-pw",
                "x-atproto-repo": "alice.bsky.social",
            },
        )

        await mw.AtprotoAuthMiddleware()._extract_credentials()

        # if set_state weren't handled, async state would stay empty (coroutine
        # discarded) and the await would raise under sync state
        assert ctx._state["atproto_handle"] == "alice.bsky.social"
        assert ctx._state["atproto_password"] == "app-pw"
        assert ctx._state["atproto_repo"] == "alice.bsky.social"


class TestHeaderFallback:
    """regression: the middleware hop can silently skip a request (it
    swallows "no active context"), which surfaced in production as one-off
    AuthenticationRequired errors on tool calls that DID carry credential
    headers. _get_credentials_from_context must fall back to reading the
    headers directly when context state is empty."""

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_falls_back_to_headers_when_state_empty(self, monkeypatch, ctx_cls):
        import fastmcp.server.dependencies as deps

        from pdsx.mcp.client import _get_credentials_from_context

        monkeypatch.setattr(deps, "get_context", lambda: ctx_cls())
        monkeypatch.setattr(
            deps,
            "get_http_headers",
            lambda include_all=True: {
                "x-atproto-handle": "alice.bsky.social",
                "x-atproto-password": "app-pw",
                "x-atproto-pds-url": "https://pds.example",
            },
        )

        creds = await _get_credentials_from_context()

        assert creds["handle"] == "alice.bsky.social"
        assert creds["password"] == "app-pw"
        assert creds["pds_url"] == "https://pds.example"

    @pytest.mark.parametrize("ctx_cls", _CONTEXT_KINDS)
    async def test_state_wins_over_headers(self, monkeypatch, ctx_cls):
        import fastmcp.server.dependencies as deps

        from pdsx.mcp.client import _get_credentials_from_context

        ctx = ctx_cls(
            {"atproto_handle": "state.bsky.social", "atproto_password": "state-pw"}
        )
        monkeypatch.setattr(deps, "get_context", lambda: ctx)
        monkeypatch.setattr(
            deps,
            "get_http_headers",
            lambda include_all=True: {
                "x-atproto-handle": "header.bsky.social",
                "x-atproto-password": "header-pw",
            },
        )

        creds = await _get_credentials_from_context()

        assert creds["handle"] == "state.bsky.social"
        assert creds["password"] == "state-pw"
