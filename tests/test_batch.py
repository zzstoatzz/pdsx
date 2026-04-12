"""tests for batch operations module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atproto import AsyncClient

from pdsx._internal.batch import (
    BatchResult,
    batch_create,
    batch_delete,
    batch_update,
    read_records_from_stdin,
    read_updates_from_stdin,
    read_uris_from_stdin,
)


@pytest.fixture
def mock_client() -> AsyncClient:
    """create a mock atproto client."""
    client = MagicMock()
    client.me = MagicMock()
    client.me.did = "did:plc:test123"
    return client


class TestBatchDelete:
    """tests for batch_delete function."""

    async def test_batch_delete_all_successful(self, mock_client: AsyncClient) -> None:
        """test batch delete with all operations successful."""
        uris = [
            "at://did:plc:test123/app.bsky.feed.post/abc123",
            "at://did:plc:test123/app.bsky.feed.post/def456",
            "at://did:plc:test123/app.bsky.feed.post/ghi789",
        ]

        with patch("pdsx._internal.batch.delete_record", new_callable=AsyncMock):
            result = await batch_delete(
                mock_client,
                uris,
                show_progress=False,
            )

        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.total == 3
        assert result.success_rate == 100.0

    async def test_batch_delete_with_failures(self, mock_client: AsyncClient) -> None:
        """test batch delete with some failures."""
        uris = [
            "at://did:plc:test123/app.bsky.feed.post/abc123",
            "at://did:plc:test123/app.bsky.feed.post/def456",
            "at://did:plc:test123/app.bsky.feed.post/ghi789",
        ]

        async def mock_delete(client: AsyncClient, uri: str) -> None:
            """mock delete that fails on second URI."""
            if "def456" in uri:
                raise ValueError("simulated failure")

        with patch("pdsx._internal.batch.delete_record", side_effect=mock_delete):
            result = await batch_delete(
                mock_client,
                uris,
                show_progress=False,
            )

        assert len(result.successful) == 2
        assert len(result.failed) == 1
        assert result.total == 3
        assert result.success_rate == pytest.approx(66.67, rel=0.01)
        assert result.failed[0][0] == "at://did:plc:test123/app.bsky.feed.post/def456"
        assert isinstance(result.failed[0][1], ValueError)

    async def test_batch_delete_fail_fast(self, mock_client: AsyncClient) -> None:
        """test batch delete with fail_fast mode."""
        uris = [
            "at://did:plc:test123/app.bsky.feed.post/abc123",
            "at://did:plc:test123/app.bsky.feed.post/def456",
            "at://did:plc:test123/app.bsky.feed.post/ghi789",
        ]

        async def mock_delete(client: AsyncClient, uri: str) -> None:
            """mock delete that fails on second URI."""
            if "def456" in uri:
                raise ValueError("simulated failure")

        with patch("pdsx._internal.batch.delete_record", side_effect=mock_delete):
            result = await batch_delete(
                mock_client,
                uris,
                fail_fast=True,
                show_progress=False,
            )

        # with fail_fast, some operations may not complete
        assert len(result.failed) >= 1
        assert result.total <= 3

    async def test_batch_delete_with_concurrency_limit(
        self, mock_client: AsyncClient
    ) -> None:
        """test batch delete respects concurrency limit."""
        import asyncio

        uris = [f"at://did:plc:test123/app.bsky.feed.post/uri{i}" for i in range(20)]

        max_concurrent = 0
        current_concurrent = 0

        async def mock_delete(client: AsyncClient, uri: str) -> None:
            """mock delete that tracks concurrency."""
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)  # simulate work
            current_concurrent -= 1

        with patch("pdsx._internal.batch.delete_record", side_effect=mock_delete):
            result = await batch_delete(
                mock_client,
                uris,
                concurrency=5,
                show_progress=False,
            )

        assert len(result.successful) == 20
        assert max_concurrent <= 5

    async def test_batch_delete_empty_list(self, mock_client: AsyncClient) -> None:
        """test batch delete with empty URI list."""
        result = await batch_delete(
            mock_client,
            [],
            show_progress=False,
        )

        assert len(result.successful) == 0
        assert len(result.failed) == 0
        assert result.total == 0


class TestBatchResult:
    """tests for BatchResult dataclass."""

    def test_batch_result_properties(self) -> None:
        """test BatchResult property calculations."""
        result = BatchResult(
            successful=["uri1", "uri2", "uri3"],
            failed=[("uri4", ValueError("error"))],
        )

        assert result.total == 4
        assert result.success_rate == 75.0

    def test_batch_result_empty(self) -> None:
        """test BatchResult with no operations."""
        result = BatchResult(successful=[], failed=[])

        assert result.total == 0
        assert result.success_rate == 0.0


class TestReadUrisFromStdin:
    """tests for read_uris_from_stdin function."""

    def test_read_from_stdin(self) -> None:
        """test reading URIs from stdin."""
        import io

        test_input = "uri1\nuri2\nuri3\n"

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            uris = read_uris_from_stdin()

        assert uris == ["uri1", "uri2", "uri3"]

    def test_read_from_stdin_with_empty_lines(self) -> None:
        """test reading URIs from stdin with empty lines."""
        import io

        test_input = "uri1\n\nuri2\n  \nuri3\n"

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            uris = read_uris_from_stdin()

        assert uris == ["uri1", "uri2", "uri3"]

    def test_read_from_stdin_strips_whitespace(self) -> None:
        """test reading URIs from stdin strips whitespace."""
        import io

        test_input = "  uri1  \n  uri2\nuri3  \n"

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            uris = read_uris_from_stdin()

        assert uris == ["uri1", "uri2", "uri3"]

    def test_read_from_tty_returns_empty(self) -> None:
        """test reading from TTY returns empty list."""
        with patch("sys.stdin.isatty", return_value=True):
            uris = read_uris_from_stdin()

        assert uris == []


class TestBatchCreate:
    """tests for batch_create function."""

    async def test_batch_create_all_successful(self, mock_client: AsyncClient) -> None:
        """test batch create with all operations successful."""
        records = [
            {"text": "post 1"},
            {"text": "post 2"},
            {"text": "post 3"},
        ]

        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:test123/app.bsky.feed.post/abc123"

        with patch(
            "pdsx._internal.batch.create_record", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_response
            result = await batch_create(
                mock_client,
                "app.bsky.feed.post",
                records,
                show_progress=False,
            )

        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.total == 3
        assert result.success_rate == 100.0

    async def test_batch_create_with_failures(self, mock_client: AsyncClient) -> None:
        """test batch create with some failures."""
        records = [
            {"text": "post 1"},
            {"text": "post 2"},
            {"text": "post 3"},
        ]

        async def mock_create(
            client: AsyncClient, collection: str, record: dict, **kwargs
        ) -> MagicMock:
            """mock create that fails on second record."""
            if record["text"] == "post 2":
                raise ValueError("simulated failure")
            mock_response = MagicMock()
            mock_response.uri = f"at://did:plc:test123/{collection}/{record['text']}"
            return mock_response

        with patch("pdsx._internal.batch.create_record", side_effect=mock_create):
            result = await batch_create(
                mock_client,
                "app.bsky.feed.post",
                records,
                show_progress=False,
            )

        assert len(result.successful) == 2
        assert len(result.failed) == 1
        assert result.total == 3
        assert result.success_rate == pytest.approx(66.67, rel=0.01)
        assert result.failed[0][0] == "record #2"
        assert isinstance(result.failed[0][1], ValueError)

    async def test_batch_create_empty_list(self, mock_client: AsyncClient) -> None:
        """test batch create with empty record list."""
        result = await batch_create(
            mock_client,
            "app.bsky.feed.post",
            [],
            show_progress=False,
        )

        assert len(result.successful) == 0
        assert len(result.failed) == 0
        assert result.total == 0


class TestReadRecordsFromStdin:
    """tests for read_records_from_stdin function."""

    def test_read_jsonl_from_stdin(self) -> None:
        """test reading JSONL records from stdin."""
        import io

        test_input = '{"text":"post 1"}\n{"text":"post 2"}\n{"text":"post 3"}\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            results = read_records_from_stdin()

        assert len(results) == 3
        assert results[0] == ({"text": "post 1"}, None)
        assert results[1] == ({"text": "post 2"}, None)
        assert results[2] == ({"text": "post 3"}, None)

    def test_read_jsonl_with_rkey(self) -> None:
        """test reading JSONL records with rkey field."""
        import io

        test_input = '{"rkey":"self","displayName":"Test"}\n{"text":"no rkey"}\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            results = read_records_from_stdin()

        assert len(results) == 2
        record, rkey = results[0]
        assert rkey == "self"
        assert "rkey" not in record  # rkey is popped from the record
        assert record == {"displayName": "Test"}
        assert results[1] == ({"text": "no rkey"}, None)

    def test_read_jsonl_with_empty_lines(self) -> None:
        """test reading JSONL with empty lines."""
        import io

        test_input = '{"text":"post 1"}\n\n{"text":"post 2"}\n  \n{"text":"post 3"}\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            results = read_records_from_stdin()

        assert len(results) == 3
        assert results[0] == ({"text": "post 1"}, None)

    def test_invalid_json_raises_error(self) -> None:
        """test invalid JSON raises ValueError."""
        import io

        test_input = '{"text":"post 1"}\ninvalid json\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: invalid JSON"),
        ):
            read_records_from_stdin()

    def test_non_object_json_raises_error(self) -> None:
        """test non-object JSON raises ValueError."""
        import io

        test_input = '{"text":"post 1"}\n["not", "an", "object"]\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: expected JSON object"),
        ):
            read_records_from_stdin()

    def test_read_from_tty_returns_empty(self) -> None:
        """test reading from TTY returns empty list."""
        with patch("sys.stdin.isatty", return_value=True):
            records = read_records_from_stdin()

        assert records == []


class TestBatchUpdate:
    """tests for batch_update function."""

    async def test_batch_update_all_successful(self, mock_client: AsyncClient) -> None:
        """test batch update with all operations successful."""
        updates = [
            ("at://did:plc:test123/app.bsky.feed.post/abc123", {"text": "updated 1"}),
            ("at://did:plc:test123/app.bsky.feed.post/def456", {"text": "updated 2"}),
            ("at://did:plc:test123/app.bsky.feed.post/ghi789", {"text": "updated 3"}),
        ]

        mock_response = MagicMock()
        mock_response.uri = "at://did:plc:test123/app.bsky.feed.post/abc123"

        with patch(
            "pdsx._internal.batch.update_record", new_callable=AsyncMock
        ) as mock_update:
            mock_update.return_value = mock_response
            result = await batch_update(
                mock_client,
                updates,
                show_progress=False,
            )

        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.total == 3
        assert result.success_rate == 100.0

    async def test_batch_update_with_failures(self, mock_client: AsyncClient) -> None:
        """test batch update with some failures."""
        updates = [
            ("at://did:plc:test123/app.bsky.feed.post/abc123", {"text": "updated 1"}),
            ("at://did:plc:test123/app.bsky.feed.post/def456", {"text": "updated 2"}),
            ("at://did:plc:test123/app.bsky.feed.post/ghi789", {"text": "updated 3"}),
        ]

        async def mock_update(
            client: AsyncClient, uri: str, updates_dict: dict
        ) -> MagicMock:
            """mock update that fails on second URI."""
            if "def456" in uri:
                raise ValueError("simulated failure")
            mock_response = MagicMock()
            mock_response.uri = uri
            return mock_response

        with patch("pdsx._internal.batch.update_record", side_effect=mock_update):
            result = await batch_update(
                mock_client,
                updates,
                show_progress=False,
            )

        assert len(result.successful) == 2
        assert len(result.failed) == 1
        assert result.total == 3
        assert result.success_rate == pytest.approx(66.67, rel=0.01)
        assert result.failed[0][0] == "at://did:plc:test123/app.bsky.feed.post/def456"
        assert isinstance(result.failed[0][1], ValueError)

    async def test_batch_update_fail_fast(self, mock_client: AsyncClient) -> None:
        """test batch update with fail_fast mode."""
        updates = [
            ("at://did:plc:test123/app.bsky.feed.post/abc123", {"text": "updated 1"}),
            ("at://did:plc:test123/app.bsky.feed.post/def456", {"text": "updated 2"}),
            ("at://did:plc:test123/app.bsky.feed.post/ghi789", {"text": "updated 3"}),
        ]

        async def mock_update(
            client: AsyncClient, uri: str, updates_dict: dict
        ) -> MagicMock:
            """mock update that fails on second URI."""
            if "def456" in uri:
                raise ValueError("simulated failure")
            mock_response = MagicMock()
            mock_response.uri = uri
            return mock_response

        with patch("pdsx._internal.batch.update_record", side_effect=mock_update):
            result = await batch_update(
                mock_client,
                updates,
                fail_fast=True,
                show_progress=False,
            )

        # with fail_fast, some operations may not complete
        assert len(result.failed) >= 1
        assert result.total <= 3

    async def test_batch_update_with_concurrency_limit(
        self, mock_client: AsyncClient
    ) -> None:
        """test batch update respects concurrency limit."""
        import asyncio

        updates = [
            (f"at://did:plc:test123/app.bsky.feed.post/uri{i}", {"text": f"text {i}"})
            for i in range(20)
        ]

        max_concurrent = 0
        current_concurrent = 0

        async def mock_update(
            client: AsyncClient, uri: str, updates_dict: dict
        ) -> MagicMock:
            """mock update that tracks concurrency."""
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.01)  # simulate work
            current_concurrent -= 1
            mock_response = MagicMock()
            mock_response.uri = uri
            return mock_response

        with patch("pdsx._internal.batch.update_record", side_effect=mock_update):
            result = await batch_update(
                mock_client,
                updates,
                concurrency=5,
                show_progress=False,
            )

        assert len(result.successful) == 20
        assert max_concurrent <= 5

    async def test_batch_update_empty_list(self, mock_client: AsyncClient) -> None:
        """test batch update with empty update list."""
        result = await batch_update(
            mock_client,
            [],
            show_progress=False,
        )

        assert len(result.successful) == 0
        assert len(result.failed) == 0
        assert result.total == 0


class TestReadUpdatesFromStdin:
    """tests for read_updates_from_stdin function."""

    def test_read_updates_from_stdin(self) -> None:
        """test reading JSONL updates from stdin."""
        import io

        test_input = (
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/abc123","text":"new text 1"}\n'
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/def456","text":"new text 2","langs":["en"]}\n'
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/ghi789","text":"new text 3"}\n'
        )

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            updates = read_updates_from_stdin()

        assert len(updates) == 3
        assert updates[0] == (
            "at://did:plc:test123/app.bsky.feed.post/abc123",
            {"text": "new text 1"},
        )
        assert updates[1] == (
            "at://did:plc:test123/app.bsky.feed.post/def456",
            {"text": "new text 2", "langs": ["en"]},
        )
        assert updates[2] == (
            "at://did:plc:test123/app.bsky.feed.post/ghi789",
            {"text": "new text 3"},
        )

    def test_read_updates_with_empty_lines(self) -> None:
        """test reading updates with empty lines."""
        import io

        test_input = (
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/abc123","text":"new text 1"}\n'
            "\n"
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/def456","text":"new text 2"}\n'
            "  \n"
            '{"uri":"at://did:plc:test123/app.bsky.feed.post/ghi789","text":"new text 3"}\n'
        )

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
        ):
            updates = read_updates_from_stdin()

        assert len(updates) == 3
        assert updates[0][0] == "at://did:plc:test123/app.bsky.feed.post/abc123"

    def test_read_updates_invalid_json_raises_error(self) -> None:
        """test invalid JSON raises ValueError."""
        import io

        test_input = '{"uri":"at://test/post/abc","text":"valid"}\ninvalid json\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: invalid JSON"),
        ):
            read_updates_from_stdin()

    def test_read_updates_missing_uri_raises_error(self) -> None:
        """test missing uri field raises ValueError."""
        import io

        test_input = (
            '{"uri":"at://test/post/abc","text":"valid"}\n{"text":"no uri field"}\n'
        )

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: missing 'uri' field"),
        ):
            read_updates_from_stdin()

    def test_read_updates_invalid_uri_type_raises_error(self) -> None:
        """test non-string uri raises ValueError."""
        import io

        test_input = '{"uri":"at://test/post/abc","text":"valid"}\n{"uri":123,"text":"uri is number"}\n'

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: 'uri' must be a string"),
        ):
            read_updates_from_stdin()

    def test_read_updates_non_object_json_raises_error(self) -> None:
        """test non-object JSON raises ValueError."""
        import io

        test_input = (
            '{"uri":"at://test/post/abc","text":"valid"}\n["not","an","object"]\n'
        )

        with (
            patch("sys.stdin", io.StringIO(test_input)),
            patch("sys.stdin.isatty", return_value=False),
            pytest.raises(ValueError, match="line 2: expected JSON object"),
        ):
            read_updates_from_stdin()

    def test_read_updates_from_tty_returns_empty(self) -> None:
        """test reading from TTY returns empty list."""
        with patch("sys.stdin.isatty", return_value=True):
            updates = read_updates_from_stdin()

        assert updates == []
