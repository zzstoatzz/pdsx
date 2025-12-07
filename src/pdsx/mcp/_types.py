"""type definitions for pdsx MCP server."""

from typing import TypedDict


class RecordResponse(TypedDict):
    """a record returned from list or get operations."""

    uri: str
    cid: str | None
    value: dict


class CreateResponse(TypedDict):
    """response from creating a record."""

    uri: str
    cid: str


class UpdateResponse(TypedDict):
    """response from updating a record."""

    uri: str
    cid: str


class DeleteResponse(TypedDict):
    """response from deleting a record."""

    deleted: str


class CredentialsContext(TypedDict):
    """credentials extracted from context or headers."""

    handle: str | None
    password: str | None
    pds_url: str | None
    repo: str | None
