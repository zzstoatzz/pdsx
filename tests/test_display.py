"""tests for display module."""

from __future__ import annotations

import pytest
from atproto_client.models.dot_dict import DotDict
from pydantic import BaseModel

from pdsx._internal.display import display_records
from pdsx._internal.output import OutputFormat


class MockPydanticValue(BaseModel):
    """mock pydantic model for testing."""

    title: str
    text: str


class MockRecord:
    """mock record for testing."""

    def __init__(self, uri: str, cid: str, value: object) -> None:
        self.uri = uri
        self.cid = cid
        self.value = value


def test_display_records_with_pydantic_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """test display_records handles pydantic models correctly."""
    value = MockPydanticValue(title="test", text="hello world")
    record = MockRecord(
        uri="at://did:example/app.bsky.feed.post/123",
        cid="cid123",
        value=value,
    )

    display_records("test.collection", [record], output_format=OutputFormat.COMPACT)  # ty: ignore[invalid-argument-type]
    captured = capsys.readouterr()

    assert "test.collection (1 record)" in captured.out
    assert '"title":"test"' in captured.out
    assert '"text":"hello world"' in captured.out


def test_display_records_with_dotdict(capsys: pytest.CaptureFixture[str]) -> None:
    """regression test for issue #1 - DotDict values should work."""
    value = DotDict({"title": "test track", "artist": "stoat", "fileType": "m4a"})
    record = MockRecord(
        uri="at://did:example/fm.plyr.track/456",
        cid="cid456",
        value=value,
    )

    display_records("fm.plyr.track", [record], output_format=OutputFormat.COMPACT)  # ty: ignore[invalid-argument-type]
    captured = capsys.readouterr()

    assert "fm.plyr.track (1 record)" in captured.out
    assert '"title":"test track"' in captured.out
    assert '"artist":"stoat"' in captured.out
    assert '"fileType":"m4a"' in captured.out


def test_display_records_with_plain_dict(capsys: pytest.CaptureFixture[str]) -> None:
    """test display_records handles plain dicts."""
    value = {"title": "test", "content": "some content"}
    record = MockRecord(
        uri="at://did:example/custom.record/789",
        cid="cid789",
        value=value,
    )

    display_records("custom.record", [record], output_format=OutputFormat.COMPACT)  # ty: ignore[invalid-argument-type]
    captured = capsys.readouterr()

    assert "custom.record (1 record)" in captured.out
    assert '"title":"test"' in captured.out
    assert '"content":"some content"' in captured.out
