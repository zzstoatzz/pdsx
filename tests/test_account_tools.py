"""tests for the opt-in account lifecycle tools."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pdsx.mcp import accounts, client

PROD_TOOLS = [
    "create_record",
    "delete_record",
    "describe_repo",
    "get_record",
    "identity_history",
    "list_records",
    "query",
    "update_record",
    "whoami",
]
ACCOUNT_TOOLS = ["create_account", "delete_account", "request_account_delete"]


def registered_tools(env: dict[str, str]) -> list[str]:
    script = (
        "import asyncio, json\n"
        "from pdsx.mcp.server import mcp\n"
        "print(json.dumps(sorted(t.name for t in asyncio.run(mcp.list_tools()))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestRegistration:
    def test_prod_tool_list_is_unchanged(self):
        env = {k: v for k, v in os.environ.items() if k != accounts.ENABLE_FLAG}
        assert registered_tools(env) == PROD_TOOLS

    @pytest.mark.parametrize("value", ["", "0", "true", "yes"])
    def test_only_exact_flag_enables(self, value):
        env = {**os.environ, accounts.ENABLE_FLAG: value}
        assert registered_tools(env) == PROD_TOOLS

    def test_flag_adds_account_tools(self):
        env = {**os.environ, accounts.ENABLE_FLAG: "1"}
        assert registered_tools(env) == sorted(PROD_TOOLS + ACCOUNT_TOOLS)


@pytest.fixture
def fake_pds(monkeypatch):
    """one fake AsyncClient class shared by the account tools and the client helper."""
    instances = []

    def make(base_url):
        instance = MagicMock()
        instance.base_url = base_url
        instance.me = None
        instance.logged_in_as = None
        server = instance.com.atproto.server
        server.create_account = AsyncMock(
            return_value=SimpleNamespace(did="did:plc:new", handle="eval.pds1.test")
        )
        server.request_account_delete = AsyncMock()
        server.delete_account = AsyncMock()
        instances.append(instance)
        return instance

    async def fake_login(instance, handle, password):
        instance.me = SimpleNamespace(did="did:plc:new", handle=handle)
        instance.logged_in_as = (handle, password)

    monkeypatch.setattr(accounts, "AsyncClient", make)
    monkeypatch.setattr(client, "AsyncClient", make)
    monkeypatch.setattr(client, "login_with_session_fallback", fake_login)
    monkeypatch.setenv("ATPROTO_HANDLE", "operator.example")
    monkeypatch.setenv("ATPROTO_PASSWORD", "operator-secret")
    monkeypatch.setenv("ATPROTO_PDS_URL", "https://pds.example")
    client.clear_active_account()
    yield instances
    client.clear_active_account()


class TestSessionSwitching:
    async def test_create_account_becomes_active_credentials(self, fake_pds):
        created = await accounts.create_account(
            "eval.pds1.test", "eval@pds1.test", "pw", pds="https://pds1.test"
        )
        assert created == {
            "did": "did:plc:new",
            "handle": "eval.pds1.test",
            "pds": "https://pds1.test",
        }
        data = fake_pds[0].com.atproto.server.create_account.await_args.args[0]
        assert (data.handle, data.email, data.password) == (
            "eval.pds1.test",
            "eval@pds1.test",
            "pw",
        )

        async with client.get_atproto_client(require_auth=True) as session:
            assert session.base_url == "https://pds1.test"
            assert session.logged_in_as == ("eval.pds1.test", "pw")

    @pytest.mark.parametrize("target", ["EVAL.pds1.test", "did:plc:new"])
    async def test_reads_of_the_new_account_skip_discovery(
        self, fake_pds, monkeypatch, target
    ):
        from pdsx._internal import resolution

        discover = AsyncMock(side_effect=AssertionError("should not discover"))
        monkeypatch.setattr(resolution, "discover_pds", discover)
        await accounts.create_account(
            "eval.pds1.test", "e@x.test", "pw", pds="https://pds1.test"
        )
        async with client.get_atproto_client(target_repo=target) as session:
            assert session.base_url == "https://pds1.test"
            assert session.logged_in_as is None

    async def test_reads_of_other_repos_still_discover(self, fake_pds, monkeypatch):
        from pdsx._internal import resolution

        discover = AsyncMock(return_value="https://elsewhere.example")
        monkeypatch.setattr(resolution, "discover_pds", discover)
        await accounts.create_account(
            "eval.pds1.test", "e@x.test", "pw", pds="https://pds1.test"
        )
        async with client.get_atproto_client(target_repo="someone.else") as session:
            assert session.base_url == "https://elsewhere.example"
        discover.assert_awaited_once_with("someone.else")

    async def test_new_handle_resolves_without_dns_until_deleted(
        self, fake_pds, monkeypatch
    ):
        from pdsx._internal import resolution

        public = MagicMock()
        public.return_value.handle.resolve = AsyncMock(return_value=None)
        monkeypatch.setattr(resolution, "AsyncIdResolver", public)
        await accounts.create_account(
            "eval.pds1.test", "e@x.test", "pw", pds="https://pds1.test"
        )
        assert await resolution.resolve_repo_did("Eval.pds1.test") == "did:plc:new"
        await accounts.delete_account("abcde-12345")
        with pytest.raises(ValueError, match="could not resolve handle"):
            await resolution.resolve_repo_did("eval.pds1.test")

    async def test_default_pds_is_the_configured_one(self, fake_pds):
        created = await accounts.create_account("eval.pds.example", "e@x.test", "pw")
        assert created["pds"] == "https://pds.example"

    async def test_without_create_account_env_credentials_apply(self, fake_pds):
        async with client.get_atproto_client(require_auth=True) as session:
            assert session.logged_in_as == ("operator.example", "operator-secret")

    async def test_failed_create_leaves_credentials_alone(self, fake_pds, monkeypatch):
        def failing(base_url):
            instance = MagicMock()
            instance.com.atproto.server.create_account = AsyncMock(
                side_effect=RuntimeError("HandleNotAvailable")
            )
            return instance

        monkeypatch.setattr(accounts, "AsyncClient", failing)
        with pytest.raises(RuntimeError):
            await accounts.create_account("taken.pds1.test", "e@x.test", "pw")
        assert client.get_active_account() is None

    async def test_request_delete_runs_as_new_account(self, fake_pds):
        await accounts.create_account(
            "eval.pds1.test", "e@x.test", "pw", pds="https://pds1.test"
        )
        result = await accounts.request_account_delete()
        assert result["requested"] == "did:plc:new"
        session = fake_pds[-1]
        assert session.logged_in_as == ("eval.pds1.test", "pw")
        session.com.atproto.server.request_account_delete.assert_awaited_once()

    async def test_delete_account_uses_did_password_and_token(self, fake_pds):
        await accounts.create_account(
            "eval.pds1.test", "e@x.test", "pw", pds="https://pds1.test"
        )
        result = await accounts.delete_account(" abcde-12345 ")
        assert result == {"deleted": "did:plc:new"}
        data = fake_pds[-1].com.atproto.server.delete_account.await_args.args[0]
        assert (data.did, data.password, data.token) == (
            "did:plc:new",
            "pw",
            "abcde-12345",
        )
        assert client.get_active_account() is None

    async def test_delete_account_needs_an_account_from_this_session(self, fake_pds):
        with pytest.raises(client.AuthenticationRequired):
            await accounts.delete_account("abcde-12345")
