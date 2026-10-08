import asyncio

import pytest
from atproto import AsyncClient

from pdsx._internal.batch import batch_create, batch_delete, batch_update


@pytest.mark.parametrize("kind", ["create", "update", "delete"])
async def test_fail_fast_stops_queued_operations_and_waits_for_completion(kind):
    client = AsyncClient()
    uri = "at://did:plc:example/io.example.record/test"
    if kind == "create":
        result = await batch_create(
            client,
            "io.example.record",
            [{}, {}, {}],
            concurrency=1,
            fail_fast=True,
            show_progress=False,
        )
    elif kind == "update":
        result = await batch_update(
            client, [(uri, {})] * 3, concurrency=1, fail_fast=True, show_progress=False
        )
    else:
        result = await batch_delete(
            client, [uri] * 3, concurrency=1, fail_fast=True, show_progress=False
        )
    assert result.total == 1
    assert len(result.failed) == 1
    assert "not authenticated" in str(result.failed[0][1])
    await asyncio.sleep(0)
    assert result.total == 1


async def test_batch_create_rejects_missing_keys_before_any_work():
    with pytest.raises(ValueError, match="one entry per record"):
        await batch_create(AsyncClient(), "io.example.record", [{}, {}], rkeys=["one"])


async def test_zero_concurrency_fails_instead_of_hanging():
    with pytest.raises(ValueError, match="concurrency must be positive"):
        await batch_delete(AsyncClient(), [], concurrency=0, show_progress=False)
