"""PDS and URI resolution utilities."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from atproto_identity.resolver import AsyncIdResolver


def normalize_service_url(host: str) -> str:
    """coerce a bare host into an https base URL.

    'pds.zat.dev' -> 'https://pds.zat.dev'; an explicit scheme is left as-is.
    """
    if host.startswith(("http://", "https://")):
        return host
    return f"https://{host}"


def reject_private_host(base_url: str) -> None:
    """raise ValueError if base_url targets a non-public address.

    Best-effort SSRF guard for read queries against arbitrary hosts: resolves
    the host and refuses loopback, private, link-local, or otherwise non-global
    addresses (e.g. cloud metadata at 169.254.169.254). This does not defend
    against DNS rebinding, so callers must not follow redirects.
    """
    host = urlparse(base_url).hostname
    if not host:
        raise ValueError(f"could not parse host from url: {base_url!r}")

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"could not resolve host {host!r}: {e}") from e

    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip.is_global:
            raise ValueError(
                f"refusing to query non-public host {host!r} (resolves to {ip})"
            )


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
