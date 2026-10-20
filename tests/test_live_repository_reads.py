import os

import pytest

from pdsx.mcp import server
from pdsx.mcp.client import get_atproto_client

pytestmark = pytest.mark.skipif(
    os.environ.get("PDSX_LIVE_READS") != "1",
    reason="opt-in public PDS integration tests",
)


@pytest.mark.parametrize("repo", ["penny.hailey.at", "phi.zzstoatzz.io"])
async def test_handle_and_did_read_the_same_repo(repo):
    described = await server.describe_repo(repo)
    assert (await server.describe_repo(described["did"])) == described
    page = await server.list_records("app.bsky.actor.profile", repo=repo, limit=1)
    assert page["results"]
    record = page["results"][0]
    key = record["uri"].rsplit("/", 1)[1]
    by_did = await server.get_record(record["uri"])
    by_handle = await server.get_record(f"at://{repo}/app.bsky.actor.profile/{key}")
    shorthand = await server.get_record(f"app.bsky.actor.profile/{key}", repo=repo)
    assert by_did == by_handle == shorthand


async def test_full_uri_overrides_unrelated_default_repo(monkeypatch):
    monkeypatch.setenv("ATPROTO_REPO", "phi.zzstoatzz.io")
    record = await server.get_record("at://penny.hailey.at/app.bsky.actor.profile/self")
    assert record["uri"].startswith("at://did:plc:m4247k3y7qpbpw5opune7nvf/")


async def test_unknown_target_does_not_fall_back_to_callers_pds():
    with pytest.raises(ValueError, match="could not resolve handle"):
        async with get_atproto_client(target_repo="does-not-exist.invalid"):
            pytest.fail("an unresolved target produced a client")


async def test_session_query_rejects_foreign_host_before_login(monkeypatch):
    monkeypatch.setenv("ATPROTO_HANDLE", "penny.hailey.at")
    monkeypatch.delenv("ATPROTO_PDS_URL", raising=False)
    with pytest.raises(ValueError, match="caller's PDS"):
        await server.query(
            "app.bsky.notification.getUnreadCount", host="https://bsky.social"
        )


async def test_penny_music_is_readable():
    page = await server.list_records("fm.plyr.track", repo="penny.hailey.at", limit=2)
    assert page["results"]
    for record in page["results"]:
        assert (await server.get_record(record["uri"]))["cid"] == record["cid"]
