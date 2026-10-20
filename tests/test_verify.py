"""tests for record proofs, bidirectional handles, and PLC history checks.

everything here is built from scratch: a throwaway secp256k1 key signs a tiny
repo (commit -> MST -> records) and a tiny PLC log, so the checks run offline.
"""

from __future__ import annotations

import base64
from typing import Any

import libipld
import pytest
from atproto_core.did_doc import DidDocument
from atproto_crypto.consts import SECP256K1_JWT_ALG
from atproto_crypto.did import format_did_key
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from pdsx._internal import identity as identity_mod
from pdsx._internal.operations import query as query_op
from pdsx._internal.verify import (
    cid_for,
    cid_str,
    mst_lookup,
    plc_did_for,
    read_car,
    verify_plc_log,
    verify_record_proof,
)
from pdsx.mcp import server

SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
DID = "did:plc:testtesttesttesttesttest"


class Key:
    def __init__(self) -> None:
        self.private = ec.generate_private_key(ec.SECP256K1())
        public = self.private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.did_key = format_did_key(SECP256K1_JWT_ALG, public)

    def sign(self, data: bytes) -> bytes:
        r, s = decode_dss_signature(self.private.sign(data, ec.ECDSA(hashes.SHA256())))
        s = min(s, SECP256K1_ORDER - s)  # atproto requires low-S
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _car(root: bytes, blocks: list[bytes]) -> bytes:
    header = libipld.encode_dag_cbor({"version": 1, "roots": [root]})
    out = _varint(len(header)) + header
    for block in blocks:
        section = cid_for(block) + block
        out += _varint(len(section)) + section
    return out


def build_repo(
    key: Key, did: str = DID, record_override: bytes | None = None
) -> tuple[dict[str, Any], list[bytes]]:
    """a signed repo with keys a | b | c, d in a two-level MST."""
    records = {
        name: libipld.encode_dag_cbor(
            {"$type": "app.bsky.feed.post", "text": f"post {name}"}
        )
        for name in "abcd"
    }
    if record_override is not None:
        records["c"] = record_override
    left = libipld.encode_dag_cbor(
        {
            "l": None,
            "e": [
                {
                    "p": 0,
                    "k": b"app.bsky.feed.post/a",
                    "v": cid_for(records["a"]),
                    "t": None,
                }
            ],
        }
    )
    right = libipld.encode_dag_cbor(
        {
            "l": None,
            "e": [
                {
                    "p": 0,
                    "k": b"app.bsky.feed.post/c",
                    "v": cid_for(records["c"]),
                    "t": None,
                },
                {"p": 19, "k": b"d", "v": cid_for(records["d"]), "t": None},
            ],
        }
    )
    root = libipld.encode_dag_cbor(
        {
            "l": cid_for(left),
            "e": [
                {
                    "p": 0,
                    "k": b"app.bsky.feed.post/b",
                    "v": cid_for(records["b"]),
                    "t": cid_for(right),
                }
            ],
        }
    )
    unsigned = {
        "did": did,
        "version": 3,
        "data": cid_for(root),
        "rev": "3l3qo2vutsw2b",
        "prev": None,
    }
    commit = libipld.encode_dag_cbor(
        {**unsigned, "sig": key.sign(libipld.encode_dag_cbor(unsigned))}
    )
    return {"commit": commit, "root": root, "left": left, "right": right}, [
        records["a"],
        records["b"],
        records["c"],
        records["d"],
    ]


def proof_car(key: Key, did: str = DID) -> bytes:
    nodes, records = build_repo(key, did)
    # path to app.bsky.feed.post/c: root -> right -> record c
    return _car(
        cid_for(nodes["commit"]),
        [nodes["commit"], nodes["root"], nodes["right"], records[2]],
    )


# -----------------------------------------------------------------------------
# record proofs
# -----------------------------------------------------------------------------


def test_valid_proof_verifies_and_returns_committed_value():
    key = Key()
    proof = verify_record_proof(
        proof_car(key), DID, "app.bsky.feed.post", "c", key.did_key
    )
    assert proof.verified, proof.reason
    assert proof.value == {"$type": "app.bsky.feed.post", "text": "post c"}
    assert proof.rev == "3l3qo2vutsw2b"
    assert proof.cid and proof.cid.startswith("bafyrei")


def test_wrong_signing_key_fails():
    proof = verify_record_proof(
        proof_car(Key()), DID, "app.bsky.feed.post", "c", Key().did_key
    )
    assert not proof.verified
    assert "signature" in (proof.reason or "")


def test_commit_for_another_did_fails():
    key = Key()
    proof = verify_record_proof(
        proof_car(key, did="did:plc:someoneelse"),
        DID,
        "app.bsky.feed.post",
        "c",
        key.did_key,
    )
    assert not proof.verified
    assert "commit is for" in (proof.reason or "")


def test_tampered_block_fails_hash_check():
    key = Key()
    car = bytearray(proof_car(key))
    car[car.rindex(b"post c") + 5] = ord("X")  # flip a byte in the record
    proof = verify_record_proof(bytes(car), DID, "app.bsky.feed.post", "c", key.did_key)
    assert not proof.verified
    assert "does not match its hash" in (proof.reason or "")


def test_swapped_record_block_is_missing_from_proof():
    """a PDS can't substitute a different record: its CID isn't the committed one."""
    key = Key()
    nodes, _ = build_repo(key)
    forged = libipld.encode_dag_cbor({"$type": "app.bsky.feed.post", "text": "forged"})
    car = _car(
        cid_for(nodes["commit"]),
        [nodes["commit"], nodes["root"], nodes["right"], forged],
    )
    proof = verify_record_proof(car, DID, "app.bsky.feed.post", "c", key.did_key)
    assert not proof.verified
    assert "missing the record block" in (proof.reason or "")


def test_mst_lookup_walks_every_branch():
    key = Key()
    nodes, records = build_repo(key)
    blocks = {cid_for(b): b for b in [*nodes.values(), *records]}
    root = cid_for(nodes["root"])
    for i, name in enumerate("abcd"):
        assert mst_lookup(blocks, root, f"app.bsky.feed.post/{name}") == cid_for(
            records[i]
        )
    assert mst_lookup(blocks, root, "app.bsky.feed.post/bb") is None
    assert mst_lookup(blocks, root, "app.bsky.feed.like/a") is None


def test_absent_record_is_reported_as_absent():
    key = Key()
    proof = verify_record_proof(
        proof_car(key), DID, "app.bsky.feed.post", "cc", key.did_key
    )
    assert not proof.verified
    assert "not in the signed repo" in (proof.reason or "")


def test_read_car_roundtrip():
    key = Key()
    root, blocks = read_car(proof_car(key))
    assert cid_str(root).startswith("bafyrei")
    assert len(blocks) == 4


# -----------------------------------------------------------------------------
# PLC audit log
# -----------------------------------------------------------------------------


def _sign_op(key: Key, op: dict[str, Any]) -> dict[str, Any]:
    sig = key.sign(libipld.encode_dag_cbor(op))
    return {**op, "sig": base64.urlsafe_b64encode(sig).decode().rstrip("=")}


def _entry(did: str, op: dict[str, Any], nullified: bool = False) -> dict[str, Any]:
    return {
        "did": did,
        "operation": op,
        "cid": cid_str(cid_for(libipld.encode_dag_cbor(op))),
        "nullified": nullified,
        "createdAt": "2026-10-20T00:00:00.000Z",
    }


def _op(rotation: Key, handle: str, pds: str, prev: str | None) -> dict[str, Any]:
    return {
        "type": "plc_operation",
        "rotationKeys": [rotation.did_key],
        "verificationMethods": {"atproto": Key().did_key},
        "alsoKnownAs": [f"at://{handle}"],
        "services": {
            "atproto_pds": {"type": "AtprotoPersonalDataServer", "endpoint": pds}
        },
        "prev": prev,
    }


def plc_log(rotation: Key) -> tuple[str, list[dict[str, Any]]]:
    genesis = _sign_op(rotation, _op(rotation, "alice.test", "https://a.pds", None))
    did = plc_did_for(genesis)
    first = _entry(did, genesis)
    moved = _sign_op(
        rotation, _op(rotation, "alice.test", "https://b.pds", first["cid"])
    )
    return did, [first, _entry(did, moved)]


def test_plc_chain_verifies_and_summarizes_migration():
    did, entries = plc_log(Key())
    history = verify_plc_log(did, entries)
    assert history.chain_verified, history.reason
    assert [op["pds"] for op in history.ops] == ["https://a.pds", "https://b.pds"]
    assert history.ops[0]["handles"] == ["at://alice.test"]


def test_plc_op_signed_by_outsider_fails():
    rotation = Key()
    did, entries = plc_log(rotation)
    hijack = _sign_op(
        Key(), _op(rotation, "mallory.test", "https://evil.pds", entries[-1]["cid"])
    )
    history = verify_plc_log(did, [*entries, _entry(did, hijack)])
    assert not history.chain_verified
    assert "not signed by a rotation key" in (history.reason or "")


def test_plc_genesis_must_hash_to_did():
    _, entries = plc_log(Key())
    history = verify_plc_log("did:plc:aaaaaaaaaaaaaaaaaaaaaaaa", entries)
    assert not history.chain_verified
    assert "does not hash to this DID" in (history.reason or "")


async def test_plc_history_for_did_web_explains_no_log():
    result = await identity_mod.plc_history("did:web:example.com")
    assert result["method"] == "web"


# -----------------------------------------------------------------------------
# bidirectional handles
# -----------------------------------------------------------------------------


class FakeResolver:
    def __init__(self, handles: dict[str, str], doc_handle: str | None) -> None:
        handle_map = handles
        doc = DidDocument.from_dict(
            {
                "id": DID,
                "alsoKnownAs": [f"at://{doc_handle}"] if doc_handle else [],
                "verificationMethod": [
                    {
                        "id": f"{DID}#atproto",
                        "type": "Multikey",
                        "controller": DID,
                        "publicKeyMultibase": Key().did_key.removeprefix("did:key:"),
                    }
                ],
                "service": [
                    {
                        "id": "#atproto_pds",
                        "type": "AtprotoPersonalDataServer",
                        "serviceEndpoint": "https://pds.example",
                    }
                ],
            }
        )

        class _Handles:
            async def resolve(self, handle: str) -> str | None:
                return handle_map.get(handle)

        class _Dids:
            async def resolve(self, did: str) -> DidDocument | None:
                return doc if did == DID else None

        self.handle = _Handles()
        self.did = _Dids()


async def test_handle_verified_both_ways():
    resolver = FakeResolver({"alice.test": DID}, "alice.test")
    ident = await identity_mod.verify_identity("alice.test", resolver)  # type: ignore[arg-type]
    assert ident.handle_verified
    assert ident.pds == "https://pds.example"
    assert ident.signing_key and ident.signing_key.startswith("did:key:z")


async def test_handle_pointing_at_did_that_does_not_claim_it():
    resolver = FakeResolver({"impostor.test": DID, "alice.test": DID}, "alice.test")
    ident = await identity_mod.verify_identity("impostor.test", resolver)  # type: ignore[arg-type]
    assert not ident.handle_verified
    assert "claims 'alice.test'" in (ident.reason or "")


async def test_did_doc_claiming_a_handle_it_does_not_control():
    resolver = FakeResolver({"bsky.app": "did:plc:someoneelse"}, "bsky.app")
    ident = await identity_mod.verify_identity(DID, resolver)  # type: ignore[arg-type]
    assert not ident.handle_verified
    assert "resolves to did:plc:someoneelse" in (ident.reason or "")


# -----------------------------------------------------------------------------
# query NSID validation
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nsid", ["../../specs/repository", "specs/repository", "a.b", "com.x.y?z=1"]
)
async def test_query_tool_rejects_non_nsid(nsid):
    result = await server.query(nsid=nsid, host="atproto.com")
    assert isinstance(result, dict)
    assert result["error"] == "invalid_nsid"


async def test_query_op_rejects_non_nsid():
    with pytest.raises(ValueError, match="not an NSID"):
        await query_op("../specs", "https://atproto.com")


# -----------------------------------------------------------------------------
# tool glue
# -----------------------------------------------------------------------------


async def test_get_record_verify_returns_the_committed_value(monkeypatch):
    key = Key()

    async def fake_fetch(did, collection, rkey):
        return verify_record_proof(proof_car(key), did, collection, rkey, key.did_key)

    monkeypatch.setattr(server, "fetch_record_proof", fake_fetch)
    result = await server.get_record(f"at://{DID}/app.bsky.feed.post/c", verify=True)

    assert result["verification"]["verified"] is True
    assert result["value"]["text"] == "post c"
    assert result["uri"] == f"at://{DID}/app.bsky.feed.post/c"
