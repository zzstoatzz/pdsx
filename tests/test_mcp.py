"""tests for pdsx MCP server."""

from pdsx.mcp._types import (
    CreateResponse,
    CredentialsContext,
    DeleteResponse,
    RecordResponse,
    UpdateResponse,
)
from pdsx.mcp.client import AUTH_HELP, AuthenticationRequired
from pdsx.mcp.filterable import apply_filter, filterable


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
