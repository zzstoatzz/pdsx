"""tests for PDS and URI resolution utilities."""

import pytest

from pdsx._internal.resolution import URIParts, discover_pds


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
    """tests for PDS discovery."""

    @pytest.mark.asyncio
    async def test_discover_pds_for_handle(self):
        """discovers PDS for a handle."""
        # using a known user on a self-hosted PDS
        pds = await discover_pds("zzstoatzz.io")
        assert pds == "https://pds.zzstoatzz.io"

    @pytest.mark.asyncio
    async def test_discover_pds_for_standard_user(self):
        """discovers PDS for a standard bsky user."""
        pds = await discover_pds("jay.bsky.team")
        # standard users are on bsky network PDS hosts
        assert "bsky.network" in pds

    @pytest.mark.asyncio
    async def test_discover_pds_for_did(self):
        """discovers PDS from DID directly."""
        # zzstoatzz.io's DID
        pds = await discover_pds("did:plc:xbtmt2zjwlrfegqvch7fboei")
        assert pds == "https://pds.zzstoatzz.io"

    @pytest.mark.asyncio
    async def test_discover_pds_invalid_handle(self):
        """raises on invalid handle."""
        with pytest.raises(ValueError, match="could not resolve handle"):
            await discover_pds("definitely.not.a.real.handle.invalid")
