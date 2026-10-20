"""cryptographic checks a model can't do in its head.

three checks, all against public data and none trusting the PDS's word:

- record proofs: ``com.atproto.sync.getRecord`` returns a CAR holding the
  signed commit, the MST nodes on the path to the record, and the record
  block. we hash every block, check the commit signature against the signing
  key in the DID document, and walk the MST from the commit's data root to
  ``collection/rkey``.
- handles: a handle is only trustworthy if it resolves to the DID *and* the
  DID document claims the handle back.
- PLC history: every op in a did:plc audit log is signed by a rotation key
  from the op it builds on, and the DID itself is the hash of the genesis op.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from typing import Any

import libipld
from atproto_crypto.did import parse_did_key
from atproto_crypto.verify import verify_signature

SHA2_256 = 0x12
DAG_CBOR = 0x71
RAW = 0x55


class ProofError(ValueError):
    """raised when a proof is malformed or does not check out."""


# -----------------------------------------------------------------------------
# CAR + CID
# -----------------------------------------------------------------------------


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data):
            raise ProofError("truncated varint in CAR")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def _read_cid(data: bytes, pos: int) -> tuple[bytes, int]:
    start = pos
    version, pos = _read_varint(data, pos)
    if version != 1:
        raise ProofError(f"unsupported CID version {version}")
    _codec, pos = _read_varint(data, pos)
    _hash_code, pos = _read_varint(data, pos)
    size, pos = _read_varint(data, pos)
    pos += size
    return data[start:pos], pos


def cid_for(data: bytes, codec: int = DAG_CBOR) -> bytes:
    """CIDv1 (sha2-256) bytes for a block."""
    return bytes([0x01, codec, SHA2_256, 0x20]) + hashlib.sha256(data).digest()


def cid_str(cid: bytes) -> str:
    return libipld.encode_cid(cid)


def read_car(data: bytes) -> tuple[bytes, dict[bytes, bytes]]:
    """parse a CARv1 into (root cid, {cid: raw block}), checking every hash.

    the atproto sdk's CAR decoder hands back decoded blocks, which loses the
    raw bytes a hash check needs, so this reads the framing directly.
    """
    header_len, pos = _read_varint(data, 0)
    header = libipld.decode_dag_cbor(data[pos : pos + header_len])
    pos += header_len
    roots = header.get("roots") if isinstance(header, dict) else None
    if not roots:
        raise ProofError("CAR has no root")

    blocks: dict[bytes, bytes] = {}
    while pos < len(data):
        section_len, pos = _read_varint(data, pos)
        end = pos + section_len
        cid, block_start = _read_cid(data, pos)
        block = data[block_start:end]
        pos = end
        codec = cid[1]
        if cid[2] != SHA2_256 or cid != cid_for(block, codec):
            raise ProofError(f"block {cid_str(cid)} does not match its hash")
        blocks[cid] = block
    return bytes(roots[0]), blocks


def ipld_to_json(value: Any) -> Any:
    """dag-cbor decoded values -> atproto JSON form ($link / $bytes)."""
    if isinstance(value, dict):
        return {k: ipld_to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [ipld_to_json(v) for v in value]
    if isinstance(value, bytes):
        # libipld decodes CID links as raw CID bytes, indistinguishable from a
        # byte string; anything that parses as a CIDv1 is treated as a link
        try:
            if value[:1] == b"\x01":
                return {"$link": libipld.encode_cid(value)}
        except ValueError:
            pass
        return {"$bytes": base64.b64encode(value).decode().rstrip("=")}
    return value


# -----------------------------------------------------------------------------
# record proofs
# -----------------------------------------------------------------------------


@dataclass
class RecordProof:
    verified: bool
    reason: str | None = None
    cid: str | None = None
    rev: str | None = None
    commit: str | None = None
    value: dict[str, Any] | None = None


def _block(blocks: dict[bytes, bytes], cid: bytes, what: str) -> Any:
    raw = blocks.get(bytes(cid))
    if raw is None:
        raise ProofError(f"proof is missing the {what} block {cid_str(cid)}")
    return libipld.decode_dag_cbor(raw)


def mst_lookup(blocks: dict[bytes, bytes], root: bytes, key: str) -> bytes | None:
    """walk the MST from root; return the value CID at key, or None if absent.

    raises ProofError if a node on the path is missing from the proof.
    """
    target = key.encode()
    node_cid: bytes | None = root
    while node_cid is not None:
        node = _block(blocks, node_cid, "MST node")
        entries = node.get("e") or []
        next_cid = node.get("l")
        prev_key = b""
        for entry in entries:
            entry_key = prev_key[: entry["p"]] + entry["k"]
            if entry_key == target:
                return bytes(entry["v"])
            if entry_key > target:
                break
            # target sorts after this entry: its subtree is the next candidate
            next_cid = entry.get("t")
            prev_key = entry_key
        node_cid = bytes(next_cid) if next_cid is not None else None
    return None


def verify_record_proof(
    car: bytes, did: str, collection: str, rkey: str, signing_key: str
) -> RecordProof:
    """check a sync.getRecord CAR against the repo's signing key (a did:key)."""
    try:
        root, blocks = read_car(car)
        commit = _block(blocks, root, "commit")
        if not isinstance(commit, dict) or "sig" not in commit:
            raise ProofError("root block is not a signed commit")
        if commit.get("did") != did:
            raise ProofError(
                f"commit is for {commit.get('did')}, not {did}",
            )
        unsigned = {k: v for k, v in commit.items() if k != "sig"}
        if not verify_signature(
            signing_key, libipld.encode_dag_cbor(unsigned), commit["sig"]
        ):
            return RecordProof(
                verified=False,
                reason="commit signature does not match the DID document's signing key",
                commit=cid_str(root),
                rev=commit.get("rev"),
            )
        value_cid = mst_lookup(blocks, bytes(commit["data"]), f"{collection}/{rkey}")
        if value_cid is None:
            return RecordProof(
                verified=False,
                reason="record is not in the signed repo (proof shows it absent)",
                commit=cid_str(root),
                rev=commit.get("rev"),
            )
        record = _block(blocks, value_cid, "record")
    except ProofError as exc:
        return RecordProof(verified=False, reason=str(exc))
    except Exception as exc:  # malformed input from a remote PDS
        return RecordProof(
            verified=False, reason=f"could not parse proof: {type(exc).__name__}: {exc}"
        )
    return RecordProof(
        verified=True,
        cid=cid_str(value_cid),
        rev=commit.get("rev"),
        commit=cid_str(root),
        value=ipld_to_json(record),
    )


# -----------------------------------------------------------------------------
# PLC audit log
# -----------------------------------------------------------------------------


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _rotation_keys(op: dict[str, Any]) -> list[str]:
    if op.get("type") == "create":  # legacy genesis format
        return [k for k in (op.get("recoveryKey"), op.get("signingKey")) if k]
    return list(op.get("rotationKeys") or [])


def _signed_by(op: dict[str, Any], keys: list[str]) -> str | None:
    sig = op.get("sig")
    if not sig:
        return None
    unsigned = libipld.encode_dag_cbor({k: v for k, v in op.items() if k != "sig"})
    signature = _b64url_decode(sig)
    for key in keys:
        try:
            parse_did_key(key)
            if verify_signature(key, unsigned, signature):
                return key
        except Exception:  # an unparseable key just doesn't match
            continue
    return None


def plc_did_for(genesis: dict[str, Any]) -> str:
    digest = hashlib.sha256(libipld.encode_dag_cbor(genesis)).digest()
    return "did:plc:" + base64.b32encode(digest).decode().lower()[:24]


@dataclass
class PlcHistory:
    did: str
    chain_verified: bool
    reason: str | None = None
    ops: list[dict[str, Any]] = field(default_factory=list)


def _summarize(op: dict[str, Any]) -> dict[str, Any]:
    if op.get("type") == "create":
        return {
            "handles": [f"at://{op['handle']}"] if op.get("handle") else [],
            "pds": op.get("service"),
            "signing_key": op.get("signingKey"),
            "rotation_keys": _rotation_keys(op),
        }
    if op.get("type") == "plc_tombstone":
        return {"tombstone": True}
    services = op.get("services") or {}
    return {
        "handles": op.get("alsoKnownAs") or [],
        "pds": (services.get("atproto_pds") or {}).get("endpoint"),
        "signing_key": (op.get("verificationMethods") or {}).get("atproto"),
        "rotation_keys": op.get("rotationKeys") or [],
    }


def verify_plc_log(did: str, entries: list[dict[str, Any]]) -> PlcHistory:
    """check a plc.directory /log/audit response and summarize each op.

    every op must be signed by a rotation key of the op its ``prev`` names,
    and the genesis op must hash to the DID.
    """
    ops: list[dict[str, Any]] = []
    by_cid: dict[str, dict[str, Any]] = {}
    failure: str | None = None

    for entry in entries:
        op = entry.get("operation") or {}
        cid = entry.get("cid")
        summary: dict[str, Any] = {
            "created_at": entry.get("createdAt"),
            "cid": cid,
            "nullified": bool(entry.get("nullified")),
            "type": op.get("type"),
            **_summarize(op),
        }
        try:
            actual_cid = cid_str(cid_for(libipld.encode_dag_cbor(op)))
            if cid and actual_cid != cid:
                raise ProofError(f"op {cid} does not hash to its cid")
            prev = op.get("prev")
            if prev is None:
                if plc_did_for(op) != did:
                    raise ProofError("genesis op does not hash to this DID")
                keys = _rotation_keys(op)
            else:
                parent = by_cid.get(prev)
                if parent is None:
                    raise ProofError(f"op {cid} builds on unknown op {prev}")
                keys = _rotation_keys(parent)
            signer = _signed_by(op, keys)
            if signer is None:
                raise ProofError(
                    f"op {cid} is not signed by a rotation key of its parent"
                )
            summary["signed_by"] = signer
        except ProofError as exc:
            failure = failure or str(exc)
        except Exception as exc:  # malformed log entry
            failure = (
                failure or f"could not check op {cid}: {type(exc).__name__}: {exc}"
            )
        if cid:
            by_cid[cid] = op
        ops.append(summary)

    if not entries:
        failure = "audit log is empty"
    return PlcHistory(did=did, chain_verified=failure is None, reason=failure, ops=ops)
