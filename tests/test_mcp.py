"""tests for pdsx MCP server."""

import json

from pdsx.mcp._types import (
    CreateResponse,
    CredentialsContext,
    DeleteResponse,
    RecordResponse,
    UpdateResponse,
)
from pdsx.mcp.client import AUTH_HELP, AuthenticationRequired
from pdsx.mcp.filterable import apply_filter, filterable
from pdsx.mcp.server import (
    MAX_LIMIT,
    MAX_RESPONSE_CHARS,
    _clean_value,
    _truncate_list_response,
)


class TestFilterable:
    """tests for the filterable decorator."""

    def test_apply_filter_no_filter(self):
        """returns data unchanged when no filter provided."""
        data = [{"a": 1}, {"a": 2}]
        result = apply_filter(data, None)
        assert result == data

    def test_apply_filter_select_field(self):
        """filters data with jmespath expression."""
        data = [{"id": 1, "name": "foo"}, {"id": 2, "name": "bar"}]
        result = apply_filter(data, "[*].id")
        assert result == [1, 2]

    def test_apply_filter_project_fields(self):
        """projects specific fields from data."""
        data = [{"id": 1, "name": "foo", "extra": "x"}]
        result = apply_filter(data, "[*].{id: id, name: name}")
        assert result == [{"id": 1, "name": "foo"}]

    def test_apply_filter_invalid_expression(self):
        """returns original data on invalid jmespath expression."""
        data = [{"a": 1}]
        result = apply_filter(data, "[[[invalid")
        assert result == data

    def test_filterable_decorator_sync(self):
        """decorator works with sync functions."""

        @filterable
        def my_func() -> list[dict]:
            return [{"id": 1, "name": "test"}]

        # without filter
        result = my_func()
        assert result == [{"id": 1, "name": "test"}]

        # with filter
        result = my_func(_filter="[*].id")
        assert result == [1]

    async def test_filterable_decorator_async(self):
        """decorator works with async functions."""

        @filterable
        async def my_func() -> list[dict]:
            return [{"id": 1, "name": "test"}]

        # without filter
        result = await my_func()
        assert result == [{"id": 1, "name": "test"}]

        # with filter
        result = await my_func(_filter="[*].id")
        assert result == [1]

    def test_filterable_preserves_signature(self):
        """decorator adds _filter parameter to signature."""
        import inspect

        @filterable
        def my_func(a: int, b: str = "default") -> list[dict]:
            return []

        sig = inspect.signature(my_func)
        params = list(sig.parameters.keys())

        assert "a" in params
        assert "b" in params
        assert "_filter" in params


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
            filterable,
            get_atproto_client,
            mcp,
        )

        assert AtprotoAuthMiddleware is not None
        assert AuthenticationRequired is not None
        assert filterable is not None
        assert get_atproto_client is not None
        assert mcp is not None


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
        assert "_filter" in result["message"]

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
