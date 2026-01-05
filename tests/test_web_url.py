"""tests for web_url module."""

from __future__ import annotations

from pdsx._internal.web_url import get_web_url


class TestBlueskyUrls:
    """tests for bluesky URL patterns."""

    def test_post_with_handle(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        url = get_web_url(uri, handle="alice.bsky.social")
        assert url == "https://bsky.app/profile/alice.bsky.social/post/xyz789"

    def test_post_with_did_fallback(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz789"
        url = get_web_url(uri)  # no handle provided
        assert url == "https://bsky.app/profile/did:plc:abc123/post/xyz789"

    def test_profile(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.actor.profile/self"
        url = get_web_url(uri, handle="bob.bsky.social")
        assert url == "https://bsky.app/profile/bob.bsky.social"

    def test_list(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.graph.list/mylist"
        url = get_web_url(uri, handle="carol.bsky.social")
        assert url == "https://bsky.app/profile/carol.bsky.social/lists/mylist"

    def test_feed_generator(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.generator/myfeed"
        url = get_web_url(uri, handle="dave.bsky.social")
        assert url == "https://bsky.app/profile/dave.bsky.social/feed/myfeed"

    def test_starterpack(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.graph.starterpack/pack1"
        url = get_web_url(uri, handle="eve.bsky.social")
        assert url == "https://bsky.app/starter-pack/eve.bsky.social/pack1"


class TestOtherAtprotoApps:
    """tests for non-bluesky ATProto apps."""

    def test_frontpage_post(self) -> None:
        uri = "at://did:plc:abc123/fyi.unravel.frontpage.post/mypost"
        url = get_web_url(uri)
        assert url == "https://frontpage.fyi/post/did:plc:abc123/mypost"

    def test_pinksea_oekaki(self) -> None:
        uri = "at://did:plc:abc123/com.shinolabs.pinksea.oekaki/drawing1"
        url = get_web_url(uri)
        assert url == "https://pinksea.art/did:plc:abc123/oekaki/drawing1"

    def test_pinksea_profile(self) -> None:
        uri = "at://did:plc:abc123/com.shinolabs.pinksea.profile/self"
        url = get_web_url(uri)
        assert url == "https://pinksea.art/did:plc:abc123"

    def test_linkat_board(self) -> None:
        uri = "at://did:plc:abc123/blue.linkat.board/self"
        url = get_web_url(uri)
        assert url == "https://linkat.blue/did:plc:abc123"

    def test_tangled_profile(self) -> None:
        uri = "at://did:plc:abc123/sh.tangled.actor.profile/self"
        url = get_web_url(uri)
        assert url == "https://tangled.org/did:plc:abc123"

    def test_tangled_repo_with_record(self) -> None:
        uri = "at://did:plc:abc123/sh.tangled.repo/somerepo"
        url = get_web_url(uri, record={"name": "my-cool-repo"})
        assert url == "https://tangled.org/did:plc:abc123/my-cool-repo"

    def test_tangled_repo_without_record(self) -> None:
        uri = "at://did:plc:abc123/sh.tangled.repo/somerepo"
        url = get_web_url(uri)  # no record provided
        assert url is None  # can't construct URL without record.name

    def test_leaflet_document(self) -> None:
        uri = "at://did:plc:abc123/pub.leaflet.document/doc1"
        url = get_web_url(uri)
        assert url == "https://leaflet.pub/p/did:plc:abc123/doc1"

    def test_leaflet_publication(self) -> None:
        uri = "at://did:plc:abc123/pub.leaflet.publication/pub1"
        url = get_web_url(uri)
        assert url == "https://leaflet.pub/lish/did:plc:abc123/pub1"


class TestEdgeCases:
    """tests for edge cases and unknown collections."""

    def test_unknown_collection_returns_none(self) -> None:
        uri = "at://did:plc:abc123/com.example.unknown/record1"
        url = get_web_url(uri)
        assert url is None

    def test_malformed_uri_returns_none(self) -> None:
        url = get_web_url("not-a-valid-uri")
        assert url is None

    def test_uri_without_rkey(self) -> None:
        # profile collections have rkey but it's not used in URL
        uri = "at://did:plc:abc123/app.bsky.actor.profile"
        url = get_web_url(uri)
        assert url == "https://bsky.app/profile/did:plc:abc123"

    def test_empty_string_returns_none(self) -> None:
        url = get_web_url("")
        assert url is None


class TestHandleVsDid:
    """tests verifying handle preference over DID."""

    def test_handle_preferred_when_provided(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz"
        # when handle is provided, it should be used instead of DID
        url = get_web_url(uri, handle="myhandle.bsky.social")
        assert url is not None
        assert "myhandle.bsky.social" in url
        assert "did:plc:abc123" not in url

    def test_did_used_when_no_handle(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz"
        url = get_web_url(uri)  # no handle
        assert url is not None
        assert "did:plc:abc123" in url

    def test_empty_handle_falls_back_to_did(self) -> None:
        uri = "at://did:plc:abc123/app.bsky.feed.post/xyz"
        url = get_web_url(uri, handle="")  # empty string
        assert url is not None
        assert "did:plc:abc123" in url
