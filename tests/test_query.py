"""tests for the read-only XRPC `query` tool and its guards."""

from typing import ClassVar

import pytest

from pdsx._internal.operations import _normalize_query_params, query
from pdsx._internal.resolution import normalize_service_url, reject_private_host
from pdsx.mcp import server

# -----------------------------------------------------------------------------
# SSRF guard
# -----------------------------------------------------------------------------


class TestRejectPrivateHost:
    """reject_private_host refuses non-public targets (IP literals, no DNS)."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1",
            "https://10.0.0.1",
            "http://192.168.1.1",
            "https://169.254.169.254",  # cloud metadata endpoint
            "http://[::1]",
        ],
    )
    def test_blocks_non_public(self, url):
        with pytest.raises(ValueError):
            reject_private_host(url)

    def test_allows_public_literal(self):
        # 8.8.8.8 is globally routable; should not raise
        reject_private_host("https://8.8.8.8")

    def test_missing_host(self):
        with pytest.raises(ValueError):
            reject_private_host("not-a-url")


# -----------------------------------------------------------------------------
# pure helpers
# -----------------------------------------------------------------------------


def test_normalize_service_url():
    assert normalize_service_url("pds.zat.dev") == "https://pds.zat.dev"
    assert normalize_service_url("https://pds.zat.dev") == "https://pds.zat.dev"
    assert normalize_service_url("http://localhost:3000") == "http://localhost:3000"


def test_normalize_query_params_lowercases_bools():
    assert _normalize_query_params({"a": True, "b": False, "c": 5, "d": "x"}) == {
        "a": "true",
        "b": "false",
        "c": 5,
        "d": "x",
    }


def test_truncate_query_response_trims_largest_list():
    big = {
        "repos": [{"did": "did:plc:" + "x" * 100} for _ in range(2000)],
        "cursor": "c",
    }
    out = server._truncate_query_response(big)
    assert out["truncated"] is True
    assert len(out["repos"]) < 2000
    assert out["cursor"] == "c"  # non-list fields preserved


def test_truncate_query_response_passthrough_small():
    small = {"did": "did:plc:abc", "handle": "alice.test"}
    assert server._truncate_query_response(small) == small


# -----------------------------------------------------------------------------
# query operation: GET-only, unauthenticated
# -----------------------------------------------------------------------------


class _RecordingResponse:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class _RecordingClient:
    """fake httpx.AsyncClient that records calls and refuses to POST."""

    instances: ClassVar[list["_RecordingClient"]] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list = []
        self.response = _RecordingResponse(
            {
                "repos": [
                    {"did": "did:plc:b64lsctzqnzpv6vd4ry3qktw"},
                    {"did": "did:plc:siv7zbedip4vcet4v67piibr"},
                ]
            }
        )
        _RecordingClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return self.response

    async def post(self, *args, **kwargs):  # pragma: no cover - must never run
        self.calls.append(("POST", args, kwargs))
        raise AssertionError("query must never issue a POST")


@pytest.fixture
def recording_client(monkeypatch):
    # skip the live SSRF DNS check; we're not making real requests
    monkeypatch.setattr(
        "pdsx._internal.operations.reject_private_host", lambda url: None
    )
    _RecordingClient.instances.clear()
    monkeypatch.setattr("pdsx._internal.operations.httpx.AsyncClient", _RecordingClient)
    return _RecordingClient


async def test_query_is_get_only_and_enumerates_repos(recording_client):
    result = await query("com.atproto.sync.listRepos", "https://pds.zat.dev")

    client = recording_client.instances[-1]
    # GET-only: exactly one GET to the xrpc path, never a POST
    assert client.calls == [
        ("GET", "https://pds.zat.dev/xrpc/com.atproto.sync.listRepos", {}),
    ]
    # redirects disabled so the SSRF guard can't be bypassed by a redirect
    assert client.kwargs.get("follow_redirects") is False
    # both residents enumerated (the bug was finding only one)
    assert [r["did"] for r in result["repos"]] == [
        "did:plc:b64lsctzqnzpv6vd4ry3qktw",
        "did:plc:siv7zbedip4vcet4v67piibr",
    ]


async def test_query_normalizes_bool_params(recording_client):
    await query(
        "app.bsky.feed.getAuthorFeed",
        "https://x.test",
        params={"reverse": True, "limit": 5},
    )
    _, _, sent = recording_client.instances[-1].calls[0]
    assert sent == {"reverse": "true", "limit": 5}


# -----------------------------------------------------------------------------
# query tool glue: target selection
# -----------------------------------------------------------------------------


async def test_query_tool_rejects_repo_and_host():
    with pytest.raises(ValueError):
        await server.query.fn(nsid="com.atproto.sync.listRepos", repo="a", host="b")


async def test_query_tool_selects_base_url(monkeypatch):
    captured: list = []

    async def fake_query(nsid, base_url, params=None):
        captured.append(base_url)
        return {"ok": True}

    async def fake_discover(repo):
        return "https://pds.example"

    monkeypatch.setattr(server, "_query", fake_query)
    monkeypatch.setattr(server, "discover_pds", fake_discover)

    await server.query.fn(nsid="com.atproto.sync.listRepos", host="pds.zat.dev")
    await server.query.fn(nsid="app.bsky.actor.getProfile", params={"actor": "a"})
    await server.query.fn(nsid="com.atproto.repo.describeRepo", repo="alice.test")

    assert captured == [
        "https://pds.zat.dev",
        server.PUBLIC_APPVIEW,
        "https://pds.example",
    ]
