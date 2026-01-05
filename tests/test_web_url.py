"""tests for web_url module."""

from __future__ import annotations

import pytest

from pdsx._internal.web_url import get_web_url


@pytest.mark.parametrize(
    ("uri", "handle", "record", "expected"),
    [
        # bluesky - posts
        (
            "at://did:plc:abc/app.bsky.feed.post/xyz",
            "alice.bsky.social",
            None,
            "https://bsky.app/profile/alice.bsky.social/post/xyz",
        ),
        (
            "at://did:plc:abc/app.bsky.feed.post/xyz",
            None,
            None,
            "https://bsky.app/profile/did:plc:abc/post/xyz",
        ),
        # bluesky - profile
        (
            "at://did:plc:abc/app.bsky.actor.profile/self",
            "bob.bsky.social",
            None,
            "https://bsky.app/profile/bob.bsky.social",
        ),
        # bluesky - list
        (
            "at://did:plc:abc/app.bsky.graph.list/mylist",
            "carol.bsky.social",
            None,
            "https://bsky.app/profile/carol.bsky.social/lists/mylist",
        ),
        # bluesky - feed generator
        (
            "at://did:plc:abc/app.bsky.feed.generator/myfeed",
            "dave.bsky.social",
            None,
            "https://bsky.app/profile/dave.bsky.social/feed/myfeed",
        ),
        # bluesky - starter pack
        (
            "at://did:plc:abc/app.bsky.graph.starterpack/pack1",
            "eve.bsky.social",
            None,
            "https://bsky.app/starter-pack/eve.bsky.social/pack1",
        ),
        # frontpage
        (
            "at://did:plc:abc/fyi.unravel.frontpage.post/mypost",
            None,
            None,
            "https://frontpage.fyi/post/did:plc:abc/mypost",
        ),
        # pinksea
        (
            "at://did:plc:abc/com.shinolabs.pinksea.oekaki/drawing1",
            None,
            None,
            "https://pinksea.art/did:plc:abc/oekaki/drawing1",
        ),
        (
            "at://did:plc:abc/com.shinolabs.pinksea.profile/self",
            None,
            None,
            "https://pinksea.art/did:plc:abc",
        ),
        # linkat
        (
            "at://did:plc:abc/blue.linkat.board/self",
            None,
            None,
            "https://linkat.blue/did:plc:abc",
        ),
        # tangled
        (
            "at://did:plc:abc/sh.tangled.actor.profile/self",
            None,
            None,
            "https://tangled.org/did:plc:abc",
        ),
        (
            "at://did:plc:abc/sh.tangled.repo/rkey",
            None,
            {"name": "my-repo"},
            "https://tangled.org/did:plc:abc/my-repo",
        ),
        (
            "at://did:plc:abc/sh.tangled.repo/rkey",
            None,
            None,
            None,  # needs record.name
        ),
        # leaflet
        (
            "at://did:plc:abc/pub.leaflet.document/doc1",
            None,
            None,
            "https://leaflet.pub/p/did:plc:abc/doc1",
        ),
        (
            "at://did:plc:abc/pub.leaflet.publication/pub1",
            None,
            None,
            "https://leaflet.pub/lish/did:plc:abc/pub1",
        ),
    ],
    ids=[
        "bsky-post-with-handle",
        "bsky-post-did-fallback",
        "bsky-profile",
        "bsky-list",
        "bsky-feed",
        "bsky-starterpack",
        "frontpage-post",
        "pinksea-oekaki",
        "pinksea-profile",
        "linkat-board",
        "tangled-profile",
        "tangled-repo-with-record",
        "tangled-repo-no-record",
        "leaflet-document",
        "leaflet-publication",
    ],
)
def test_web_url_patterns(
    uri: str,
    handle: str | None,
    record: dict | None,
    expected: str | None,
) -> None:
    """test URL generation for all supported ATProto apps."""
    url = get_web_url(uri, handle=handle, record=record)
    assert url == expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("at://did:plc:abc/com.example.unknown/r1", None),
        ("not-a-valid-uri", None),
        ("", None),
        (
            "at://did:plc:abc/app.bsky.actor.profile",
            "https://bsky.app/profile/did:plc:abc",
        ),
    ],
    ids=["unknown-collection", "malformed-uri", "empty-string", "uri-without-rkey"],
)
def test_edge_cases(uri: str, expected: str | None) -> None:
    """test edge cases and error handling."""
    assert get_web_url(uri) == expected


@pytest.mark.parametrize(
    ("handle", "expected_contains", "expected_not_contains"),
    [
        ("myhandle.bsky.social", "myhandle.bsky.social", "did:plc:abc"),
        (None, "did:plc:abc", None),
        ("", "did:plc:abc", None),
    ],
    ids=["handle-preferred", "did-fallback", "empty-handle-fallback"],
)
def test_handle_vs_did_preference(
    handle: str | None,
    expected_contains: str,
    expected_not_contains: str | None,
) -> None:
    """test that handle is preferred over DID when provided."""
    uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
    url = get_web_url(uri, handle=handle)
    assert url is not None
    assert expected_contains in url
    if expected_not_contains:
        assert expected_not_contains not in url
