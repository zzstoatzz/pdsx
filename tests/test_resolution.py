"""tests for PDS and URI resolution utilities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pdsx._internal.resolution import URIParts, discover_pds

HANDLE = "alice.example.test"
DID = "did:plc:fixturefixturefixture00"
PDS = "https://pds.example.test"


class TestURIParts:
    """tests for URIParts parsing."""

    def test_full_uri(self):
        """parses full AT-URI correctly."""
        parts = URIParts.from_uri("at://did:plc:abc123/app.bsky.feed.post/xyz789")
        assert parts.repo == "did:plc:abc123"
        assert parts.collection == "app.bsky.feed.post"
        assert parts.rkey == "xyz789"

    def test_shorthand_uri_with_did(self):
        """parses shorthand URI with provided DID."""
        parts = URIParts.from_uri("app.bsky.feed.post/xyz789", client_did="did:plc:abc")
        assert parts.repo == "did:plc:abc"
        assert parts.collection == "app.bsky.feed.post"
        assert parts.rkey == "xyz789"

    def test_shorthand_uri_without_did_raises(self):
        """raises when shorthand URI used without DID."""
        with pytest.raises(ValueError, match="shorthand URI requires authentication"):
            URIParts.from_uri("app.bsky.feed.post/xyz789")

    def test_invalid_uri_raises(self):
        """raises on invalid URI format."""
        with pytest.raises(ValueError, match="invalid URI format"):
            URIParts.from_uri("just/a/bad/path/here")


class TestDiscoverPds:
    """tests for PDS discovery, with identity resolution faked."""

    @pytest.fixture
    def resolver(self, mocker):
        resolver = MagicMock()
        resolver.handle.resolve = AsyncMock(
            side_effect=lambda handle: {HANDLE: DID}.get(handle)
        )
        resolver.did.resolve_atproto_data = AsyncMock(
            side_effect=lambda did: SimpleNamespace(pds=PDS) if did == DID else None
        )
        mocker.patch("pdsx._internal.resolution.AsyncIdResolver", return_value=resolver)
        return resolver

    async def test_discover_pds_for_handle(self, resolver):
        """resolves a handle to its DID, then the DID document to its PDS."""
        assert await discover_pds(HANDLE) == PDS
        resolver.handle.resolve.assert_awaited_once_with(HANDLE)
        resolver.did.resolve_atproto_data.assert_awaited_once_with(DID)

    async def test_discover_pds_for_did(self, resolver):
        """resolves a DID document directly, without handle resolution."""
        assert await discover_pds(DID) == PDS
        resolver.handle.resolve.assert_not_awaited()
        resolver.did.resolve_atproto_data.assert_awaited_once_with(DID)

    async def test_discover_pds_invalid_handle(self, resolver):
        """raises on a handle that does not resolve."""
        with pytest.raises(ValueError, match="could not resolve handle"):
            await discover_pds("definitely.not.a.real.handle.invalid")

    async def test_discover_pds_without_did_document(self, resolver):
        """raises when the DID document cannot be resolved."""
        with pytest.raises(ValueError, match="could not find PDS"):
            await discover_pds("did:plc:unknown")
