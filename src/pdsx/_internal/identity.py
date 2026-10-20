"""identity checks: bidirectional handles, record proofs, PLC history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx
from atproto_core.exceptions import AtProtocolError
from atproto_identity.resolver import AsyncIdResolver

from pdsx._internal.resolution import reject_private_host
from pdsx._internal.verify import (
    RecordProof,
    verify_plc_log,
    verify_record_proof,
)

PLC_DIRECTORY = "https://plc.directory"


@dataclass
class Identity:
    did: str
    handle: str | None
    handle_verified: bool
    pds: str | None
    signing_key: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def verify_identity(
    repo: str, resolver: AsyncIdResolver | None = None
) -> Identity:
    """resolve a handle or DID and check the handle in both directions.

    a handle only counts as verified when it resolves to the DID *and* the
    DID document lists it in alsoKnownAs. either half alone can be forged:
    anyone can put any handle in their own DID document, and a DNS record
    can point at any DID.
    """
    resolver = resolver or AsyncIdResolver()
    claimed_handle = None if repo.startswith("did:") else repo.lower()
    if claimed_handle:
        did = await resolver.handle.resolve(claimed_handle)
        if not did:
            raise ValueError(f"could not resolve handle: {repo}")
    else:
        did = repo

    doc = await resolver.did.resolve(did)
    if doc is None:
        raise ValueError(f"could not resolve DID document for: {did}")
    doc_handle = doc.get_handle()
    doc_handle = doc_handle.lower() if doc_handle else None

    reason = None
    if doc_handle is None:
        verified = False
        reason = "DID document claims no handle"
    elif claimed_handle and doc_handle != claimed_handle:
        verified = False
        reason = f"DID document claims {doc_handle!r}, not {claimed_handle!r}"
    else:
        back = await resolver.handle.resolve(doc_handle)
        verified = back == did
        if not verified:
            reason = f"{doc_handle!r} resolves to {back or 'nothing'}, not {did}"

    return Identity(
        did=did,
        handle=doc_handle,
        handle_verified=verified,
        pds=doc.get_pds_endpoint(),
        signing_key=doc.get_did_key(),
        reason=reason,
    )


async def fetch_record_proof(
    did: str,
    collection: str,
    rkey: str,
    resolver: AsyncIdResolver | None = None,
    timeout: float = 10.0,
) -> RecordProof:
    """fetch sync.getRecord from the repo's own PDS and verify it.

    the signing key and PDS come from the DID document, never from the PDS.
    """
    resolver = resolver or AsyncIdResolver()
    try:
        doc = await resolver.did.resolve(did)
        if doc is None:
            return RecordProof(verified=False, reason=f"could not resolve {did}")
        pds, key = doc.get_pds_endpoint(), doc.get_did_key()
        if not pds or not key:
            return RecordProof(
                verified=False, reason="DID document has no PDS endpoint or signing key"
            )
        reject_private_host(pds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(
                f"{pds.rstrip('/')}/xrpc/com.atproto.sync.getRecord",
                params={"did": did, "collection": collection, "rkey": rkey},
            )
    except (AtProtocolError, httpx.HTTPError, ValueError) as exc:
        return RecordProof(verified=False, reason=f"could not fetch proof: {exc}")
    if response.status_code != 200:
        return RecordProof(
            verified=False,
            reason=f"PDS answered sync.getRecord with {response.status_code}: "
            f"{response.text[:200]}",
        )
    return verify_record_proof(response.content, did, collection, rkey, key)


async def plc_history(did: str, timeout: float = 10.0) -> dict[str, Any]:
    """the did:plc audit log, each op checked and summarized."""
    if did.startswith("did:web:"):
        return {
            "did": did,
            "method": "web",
            "message": "did:web has no history: the document is whatever the "
            "domain serves now, and control follows control of the domain.",
        }
    if not did.startswith("did:plc:"):
        raise ValueError(f"expected a did:plc or did:web, got {did!r}")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(f"{PLC_DIRECTORY}/{did}/log/audit")
        response.raise_for_status()
        entries = response.json()
    return {"method": "plc", **asdict(verify_plc_log(did, entries))}
