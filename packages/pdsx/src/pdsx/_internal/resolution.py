"""PDS and URI resolution utilities."""

from __future__ import annotations

from dataclasses import dataclass

from atproto_identity.resolver import AsyncIdResolver


@dataclass
class URIParts:
    """parsed components of an AT-URI."""

    repo: str
    collection: str
    rkey: str

    @classmethod
    def from_uri(cls, uri: str, client_did: str | None = None) -> URIParts:
        """parse an AT-URI into its components.

        Args:
            uri: either full AT-URI (at://did/collection/rkey) or shorthand (collection/rkey)
            client_did: authenticated user's DID (required for shorthand format)

        Returns:
            URIParts with repo, collection, and rkey

        Raises:
            ValueError: if URI format is invalid or shorthand used without authentication
        """
        # strip at:// prefix if present
        uri_without_prefix = uri.replace("at://", "")
        parts = uri_without_prefix.split("/")

        # shorthand format: collection/rkey
        if len(parts) == 2:
            if not client_did:
                raise ValueError("shorthand URI requires authentication")
            return cls(repo=client_did, collection=parts[0], rkey=parts[1])

        # full format: did/collection/rkey
        if len(parts) == 3:
            return cls(repo=parts[0], collection=parts[1], rkey=parts[2])

        raise ValueError(f"invalid URI format: {uri}")


async def discover_pds(repo: str) -> str:
    """discover PDS URL from handle or DID.

    Args:
        repo: handle (e.g., 'zzstoatzz.io') or DID (e.g., 'did:plc:...')

    Returns:
        PDS URL (e.g., 'https://pds.zzstoatzz.io')

    Raises:
        ValueError: if handle cannot be resolved or PDS not found
    """
    resolver = AsyncIdResolver()

    # if repo looks like a DID, use it directly; otherwise resolve handle to DID
    if repo.startswith("did:"):
        did = repo
    else:
        did = await resolver.handle.resolve(repo)
        if not did:
            raise ValueError(f"could not resolve handle: {repo}")

    # resolve DID to atproto data which includes PDS URL
    atproto_data = await resolver.did.resolve_atproto_data(did)
    if not atproto_data or not atproto_data.pds:
        raise ValueError(f"could not find PDS for: {repo}")

    return atproto_data.pds
