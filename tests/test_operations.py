"""tests for operations module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from atproto import AsyncClient, models

from pdsx._internal.operations import (
    delete_record,
    describe_repo,
    get_record,
    list_records,
    update_record,
)


@pytest.fixture
def mock_client() -> AsyncClient:
    """create a mock atproto client."""
    client = MagicMock()
    client.me = MagicMock()
    client.me.did = "did:plc:test123"
    return client


@pytest.fixture
def mock_client_no_auth() -> AsyncClient:
    """create a mock atproto client without authentication."""
    client = MagicMock()
    client.me = None
    return client


class TestGetRecord:
    """tests for get_record function."""

    async def test_full_uri_format(self, mock_client: AsyncClient) -> None:
        """test get with full at:// URI format."""
        mock_client.com.atproto.repo.get_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=models.ComAtprotoRepoGetRecord.Response(
                uri="at://did:plc:test123/app.bsky.actor.profile/self",
                cid="testcid",
                value={"description": "my bio"},
            )
        )

        result = await get_record(
            mock_client,
            "at://did:plc:test123/app.bsky.actor.profile/self",
        )

        assert result.uri == "at://did:plc:test123/app.bsky.actor.profile/self"
        mock_client.com.atproto.repo.get_record.assert_called_once()
        call_args = mock_client.com.atproto.repo.get_record.call_args[0][0]
        assert call_args["repo"] == "did:plc:test123"
        assert call_args["collection"] == "app.bsky.actor.profile"
        assert call_args["rkey"] == "self"

    async def test_shorthand_uri_format(self, mock_client: AsyncClient) -> None:
        """test get with shorthand URI format (collection/rkey)."""
        mock_client.com.atproto.repo.get_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=models.ComAtprotoRepoGetRecord.Response(
                uri="at://did:plc:test123/app.bsky.actor.profile/self",
                cid="testcid",
                value={"description": "my bio"},
            )
        )

        await get_record(
            mock_client,
            "app.bsky.actor.profile/self",
        )

        # verify it used client.me.did
        mock_client.com.atproto.repo.get_record.assert_called_once()
        call_args = mock_client.com.atproto.repo.get_record.call_args[0][0]
        assert call_args["repo"] == "did:plc:test123"
        assert call_args["collection"] == "app.bsky.actor.profile"
        assert call_args["rkey"] == "self"

    async def test_shorthand_uri_without_auth_fails(
        self, mock_client_no_auth: AsyncClient
    ) -> None:
        """test shorthand URI fails without authentication."""
        with pytest.raises(ValueError, match="shorthand URI requires authentication"):
            await get_record(
                mock_client_no_auth,
                "app.bsky.actor.profile/self",
            )

    async def test_invalid_uri_format_fails(self, mock_client: AsyncClient) -> None:
        """test invalid URI format raises error."""
        with pytest.raises(ValueError, match="invalid URI format"):
            await get_record(
                mock_client,
                "invalid",
            )


class TestUpdateRecord:
    """tests for update_record function."""

    async def test_full_uri_format(self, mock_client: AsyncClient) -> None:
        """test update with full at:// URI format."""
        mock_client.com.atproto.repo.get_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=MagicMock(value={"description": "old bio"})
        )
        mock_client.com.atproto.repo.put_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=models.ComAtprotoRepoPutRecord.Response(
                uri="at://did:plc:test123/app.bsky.actor.profile/self",
                cid="testcid",
            )
        )

        result = await update_record(
            mock_client,
            "at://did:plc:test123/app.bsky.actor.profile/self",
            {"description": "new bio"},
        )

        assert result.uri == "at://did:plc:test123/app.bsky.actor.profile/self"
        mock_client.com.atproto.repo.put_record.assert_called_once()

    async def test_shorthand_uri_format(self, mock_client: AsyncClient) -> None:
        """test update with shorthand URI format (collection/rkey)."""
        mock_client.com.atproto.repo.get_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=MagicMock(value={"description": "old bio"})
        )
        mock_client.com.atproto.repo.put_record = AsyncMock(  # type: ignore[attr-defined]
            return_value=models.ComAtprotoRepoPutRecord.Response(
                uri="at://did:plc:test123/app.bsky.actor.profile/self",
                cid="testcid",
            )
        )

        await update_record(
            mock_client,
            "app.bsky.actor.profile/self",
            {"description": "new bio"},
        )

        # verify it used client.me.did
        mock_client.com.atproto.repo.get_record.assert_called_once()
        call_args = mock_client.com.atproto.repo.get_record.call_args[0][0]
        assert call_args["repo"] == "did:plc:test123"
        assert call_args["collection"] == "app.bsky.actor.profile"
        assert call_args["rkey"] == "self"

    async def test_shorthand_uri_without_auth_fails(
        self, mock_client_no_auth: AsyncClient
    ) -> None:
        """test shorthand URI fails without authentication."""
        with pytest.raises(ValueError, match="shorthand URI requires authentication"):
            await update_record(
                mock_client_no_auth,
                "app.bsky.actor.profile/self",
                {"description": "new bio"},
            )

    async def test_invalid_uri_format_fails(self, mock_client: AsyncClient) -> None:
        """test invalid URI format raises error."""
        with pytest.raises(ValueError, match="invalid URI format"):
            await update_record(
                mock_client,
                "invalid/uri/format/too/many/parts",
                {"description": "new bio"},
            )


class TestDeleteRecord:
    """tests for delete_record function."""

    async def test_full_uri_format(self, mock_client: AsyncClient) -> None:
        """test delete with full at:// URI format."""
        mock_client.com.atproto.repo.delete_record = AsyncMock()  # type: ignore[attr-defined]

        await delete_record(
            mock_client,
            "at://did:plc:test123/app.bsky.feed.post/abc123",
        )

        mock_client.com.atproto.repo.delete_record.assert_called_once()
        call_args = mock_client.com.atproto.repo.delete_record.call_args[0][0]
        assert call_args["repo"] == "did:plc:test123"
        assert call_args["collection"] == "app.bsky.feed.post"
        assert call_args["rkey"] == "abc123"

    async def test_shorthand_uri_format(self, mock_client: AsyncClient) -> None:
        """test delete with shorthand URI format (collection/rkey)."""
        mock_client.com.atproto.repo.delete_record = AsyncMock()  # type: ignore[attr-defined]

        await delete_record(
            mock_client,
            "app.bsky.feed.post/abc123",
        )

        # verify it used client.me.did
        mock_client.com.atproto.repo.delete_record.assert_called_once()
        call_args = mock_client.com.atproto.repo.delete_record.call_args[0][0]
        assert call_args["repo"] == "did:plc:test123"
        assert call_args["collection"] == "app.bsky.feed.post"
        assert call_args["rkey"] == "abc123"

    async def test_shorthand_uri_without_auth_fails(
        self, mock_client_no_auth: AsyncClient
    ) -> None:
        """test shorthand URI fails without authentication."""
        with pytest.raises(ValueError, match="shorthand URI requires authentication"):
            await delete_record(
                mock_client_no_auth,
                "app.bsky.feed.post/abc123",
            )

    async def test_invalid_uri_format_fails(self, mock_client: AsyncClient) -> None:
        """test invalid URI format raises error."""
        with pytest.raises(ValueError, match="invalid URI format"):
            await delete_record(
                mock_client,
                "invalid",
            )


class TestListRecords:
    """tests for list_records function."""

    async def test_list_records_without_cursor(self, mock_client: AsyncClient) -> None:
        """test listing records without cursor."""
        mock_response = models.ComAtprotoRepoListRecords.Response(
            records=[],
            cursor=None,
        )
        mock_client.com.atproto.repo.list_records = AsyncMock(  # type: ignore[attr-defined]
            return_value=mock_response
        )

        result = await list_records(
            mock_client,
            "app.bsky.feed.post",
            limit=50,
        )

        assert result == mock_response
        mock_client.com.atproto.repo.list_records.assert_called_once()
        call_args = mock_client.com.atproto.repo.list_records.call_args[0][0]
        assert call_args["collection"] == "app.bsky.feed.post"
        assert call_args["limit"] == 50
        assert "cursor" not in call_args

    async def test_list_records_with_cursor(self, mock_client: AsyncClient) -> None:
        """test listing records with cursor for pagination."""
        mock_response = models.ComAtprotoRepoListRecords.Response(
            records=[],
            cursor="next_page_cursor",
        )
        mock_client.com.atproto.repo.list_records = AsyncMock(  # type: ignore[attr-defined]
            return_value=mock_response
        )

        result = await list_records(
            mock_client,
            "app.bsky.feed.post",
            limit=50,
            cursor="previous_cursor",
        )

        assert result == mock_response
        mock_client.com.atproto.repo.list_records.assert_called_once()
        call_args = mock_client.com.atproto.repo.list_records.call_args[0][0]
        assert call_args["collection"] == "app.bsky.feed.post"
        assert call_args["limit"] == 50
        assert call_args["cursor"] == "previous_cursor"


class TestDescribeRepo:
    """tests for describe_repo function."""

    async def test_describe_repo(self, mock_client: AsyncClient) -> None:
        """test describing a repo returns collections."""
        mock_response = models.ComAtprotoRepoDescribeRepo.Response(
            handle="test.bsky.social",
            did="did:plc:test123",
            did_doc={},
            collections=["app.bsky.feed.post", "app.bsky.actor.profile"],
            handle_is_correct=True,
        )
        mock_client.com.atproto.repo.describe_repo = AsyncMock(  # type: ignore[attr-defined]
            return_value=mock_response
        )

        result = await describe_repo(mock_client, "test.bsky.social")

        assert result.handle == "test.bsky.social"
        assert result.did == "did:plc:test123"
        assert result.collections == [
            "app.bsky.feed.post",
            "app.bsky.actor.profile",
        ]
        assert result.handle_is_correct is True
        mock_client.com.atproto.repo.describe_repo.assert_called_once_with(
            {"repo": "test.bsky.social"}
        )

    async def test_describe_repo_no_auth_needed(
        self, mock_client_no_auth: AsyncClient
    ) -> None:
        """test describe_repo works without authentication."""
        mock_response = models.ComAtprotoRepoDescribeRepo.Response(
            handle="other.bsky.social",
            did="did:plc:other456",
            did_doc={},
            collections=["app.bsky.feed.post"],
            handle_is_correct=True,
        )
        mock_client_no_auth.com.atproto.repo.describe_repo = AsyncMock(  # type: ignore[attr-defined]
            return_value=mock_response
        )

        result = await describe_repo(mock_client_no_auth, "other.bsky.social")

        assert result.handle == "other.bsky.social"
        assert result.collections == ["app.bsky.feed.post"]
