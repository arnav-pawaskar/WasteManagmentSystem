"""
Permissioned append-only ledger for the fog-based waste management system.

Implements the blockchain layer described in Section IV-D of the paper: every
significant operational event -- bin service confirmations, route completions,
spillover transfers, and zone-state snapshots -- is committed to an append-only,
hash-chained ledger. Each transaction encodes event type, zone ID, timestamp, and a
SHA-256 hash of its payload, and is signed by the committing fog node. Blocks are
committed only after endorsement by a quorum of a fixed validator set, which is the
arrangement a permissioned setting makes possible when participants (municipality,
contractors, recyclers) are known in advance.

Standard library only, so the fog software still runs on inexpensive edge hardware
without a dependency footprint.

SCOPE AND LIMITATIONS -- read before citing this module:

  * Signatures are HMAC-SHA256 over a per-node key held by the registry. This is a
    symmetric scheme: any party able to verify a signature is also able to forge one.
    It demonstrates the commit/verify pipeline, not production authentication. A real
    deployment requires asymmetric signatures (e.g. ECDSA) so that verification does
    not confer signing capability.
  * Quorum endorsement is PBFT-shaped (2f+1 of 3f+1) but is not a PBFT implementation:
    there is no view change, no primary election, and no protection against equivocation
    by a faulty proposer.
  * The ledger is in-process. There is no network consensus, no persistence, and no
    integration with a production platform such as Hyperledger Fabric.

These limitations are stated in Section V-E of the paper.
"""

import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EventType(Enum):
    """The four operational events the paper commits to the ledger."""
    BIN_SERVICED = "BIN_SERVICED"
    ROUTE_COMPLETED = "ROUTE_COMPLETED"
    SPILLOVER_TRANSFER = "SPILLOVER_TRANSFER"
    ZONE_SNAPSHOT = "ZONE_SNAPSHOT"


def canonical_json(obj: Any) -> str:
    """Deterministic serialisation, so a payload always hashes to the same digest."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Transaction:
    """A single signed operational event."""
    event_type: str
    zone_id: int
    timestamp: str          # ISO-8601, part of the signed material
    payload: Dict[str, Any]
    payload_hash: str       # SHA-256 over the canonical payload
    committer_id: str
    signature: str

    def signing_material(self) -> str:
        """Exactly the fields covered by the committer's signature."""
        return canonical_json({
            "event_type": self.event_type,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp,
            "payload_hash": self.payload_hash,
            "committer_id": self.committer_id,
        })

    def digest(self) -> str:
        """Transaction identity, used as the Merkle leaf."""
        return sha256_hex(self.signing_material() + self.signature)

    def payload_matches(self) -> bool:
        """Detect tampering with the payload after signing."""
        return self.payload_hash == sha256_hex(canonical_json(self.payload))


@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: str
    transactions: List[Transaction]
    merkle_root: str
    block_hash: str
    endorsements: Dict[str, str] = field(default_factory=dict)

    def header_material(self) -> str:
        return canonical_json({
            "index": self.index,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "merkle_root": self.merkle_root,
        })

    def recompute_hash(self) -> str:
        return sha256_hex(self.header_material())


def merkle_root(tx_digests: List[str]) -> str:
    """Binary Merkle root; empty tree hashes the empty string."""
    if not tx_digests:
        return sha256_hex("")
    level = list(tx_digests)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])          # duplicate the odd tail
        level = [sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


class ValidatorRegistry:
    """
    Fixed validator set for the permissioned network.

    Keys are distributed out of band at network formation, which is what makes the
    setting permissioned: membership is known in advance rather than open.
    """

    def __init__(self):
        self._keys: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def register(self, node_id: str, key: Optional[bytes] = None) -> bytes:
        with self._lock:
            if key is None:
                key = os.urandom(32)
            self._keys[node_id] = key
            return key

    def is_validator(self, node_id: str) -> bool:
        return node_id in self._keys

    @property
    def validators(self) -> List[str]:
        return sorted(self._keys)

    @property
    def size(self) -> int:
        return len(self._keys)

    @property
    def fault_tolerance(self) -> int:
        """Byzantine faults tolerable at this size: largest f with n >= 3f+1."""
        return max(0, (self.size - 1) // 3)

    @property
    def quorum_size(self) -> int:
        """
        Endorsements required to commit: 2f+1.

        Note that at n=3 this yields f=0 and quorum=1 -- three validators cannot
        tolerate a Byzantine fault. Tolerating one requires n>=4.
        """
        return min(self.size, 2 * self.fault_tolerance + 1) if self.size else 0

    def sign(self, node_id: str, message: str) -> str:
        key = self._keys.get(node_id)
        if key is None:
            raise KeyError(f"{node_id} is not a registered validator")
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, node_id: str, message: str, signature: str) -> bool:
        key = self._keys.get(node_id)
        if key is None:
            return False
        expected = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class PermissionedLedger:
    """Append-only hash-chained ledger with quorum-endorsed blocks."""

    GENESIS_PREV = "0" * 64

    def __init__(self, registry: ValidatorRegistry, block_size: int = 8):
        self.registry = registry
        self.block_size = block_size
        self.chain: List[Block] = []
        self.pending: List[Transaction] = []
        self._lock = threading.RLock()
        self._rejected = 0
        self._append_genesis()

    def _append_genesis(self):
        root = merkle_root([])
        blk = Block(
            index=0,
            prev_hash=self.GENESIS_PREV,
            timestamp=datetime.now().isoformat(),
            transactions=[],
            merkle_root=root,
            block_hash="",
        )
        blk.block_hash = blk.recompute_hash()
        self.chain.append(blk)

    # ---------- submission ----------

    def submit(self, event_type: EventType, zone_id: int,
               payload: Dict[str, Any], committer_id: str,
               timestamp: Optional[datetime] = None) -> Transaction:
        """Sign an operational event and queue it for the next block."""
        ts = (timestamp or datetime.now()).isoformat()
        payload_hash = sha256_hex(canonical_json(payload))
        unsigned = canonical_json({
            "event_type": event_type.value,
            "zone_id": zone_id,
            "timestamp": ts,
            "payload_hash": payload_hash,
            "committer_id": committer_id,
        })
        signature = self.registry.sign(committer_id, unsigned)
        tx = Transaction(
            event_type=event_type.value,
            zone_id=zone_id,
            timestamp=ts,
            payload=dict(payload),
            payload_hash=payload_hash,
            committer_id=committer_id,
            signature=signature,
        )
        with self._lock:
            self.pending.append(tx)
            if len(self.pending) >= self.block_size:
                self.seal_block(committer_id)
        return tx

    # ---------- block lifecycle ----------

    def propose_block(self, proposer_id: str) -> Optional[Block]:
        with self._lock:
            if not self.pending:
                return None
            txs = list(self.pending)
            head = self.chain[-1]
            root = merkle_root([t.digest() for t in txs])
            blk = Block(
                index=head.index + 1,
                prev_hash=head.block_hash,
                timestamp=datetime.now().isoformat(),
                transactions=txs,
                merkle_root=root,
                block_hash="",
            )
            blk.block_hash = blk.recompute_hash()
            self.endorse(blk, proposer_id)
            return blk

    def endorse(self, block: Block, validator_id: str) -> bool:
        """A validator endorses a proposed block by signing its header."""
        if not self.registry.is_validator(validator_id):
            return False
        block.endorsements[validator_id] = self.registry.sign(
            validator_id, block.header_material())
        return True

    def commit_block(self, block: Block) -> bool:
        """Append a block once it carries a quorum of valid endorsements."""
        with self._lock:
            head = self.chain[-1]
            if block.prev_hash != head.block_hash or block.index != head.index + 1:
                self._rejected += 1
                return False
            valid = sum(
                1 for v, sig in block.endorsements.items()
                if self.registry.verify(v, block.header_material(), sig)
            )
            if valid < max(1, self.registry.quorum_size):
                self._rejected += 1
                return False
            self.chain.append(block)
            committed = {t.digest() for t in block.transactions}
            self.pending = [t for t in self.pending if t.digest() not in committed]
            return True

    def seal_block(self, proposer_id: str) -> Optional[Block]:
        """Propose, collect endorsements from every validator, and commit."""
        with self._lock:
            blk = self.propose_block(proposer_id)
            if blk is None:
                return None
            for v in self.registry.validators:
                self.endorse(blk, v)
            return blk if self.commit_block(blk) else None

    def flush(self, proposer_id: str) -> Optional[Block]:
        """Seal any remaining pending transactions (call at shutdown)."""
        with self._lock:
            return self.seal_block(proposer_id) if self.pending else None

    # ---------- verification ----------

    def verify_chain(self) -> Tuple[bool, List[str]]:
        """
        Independent audit: any stakeholder can call this without a trusted
        intermediary. Checks hash linkage, block hashes, Merkle roots, payload
        integrity, committer signatures, and endorsement quorum.
        """
        problems: List[str] = []
        with self._lock:
            for i, blk in enumerate(self.chain):
                if blk.block_hash != blk.recompute_hash():
                    problems.append(f"block {i}: header hash mismatch")
                expected_prev = self.GENESIS_PREV if i == 0 else self.chain[i - 1].block_hash
                if blk.prev_hash != expected_prev:
                    problems.append(f"block {i}: broken chain linkage")
                if blk.merkle_root != merkle_root([t.digest() for t in blk.transactions]):
                    problems.append(f"block {i}: Merkle root mismatch")

                for j, tx in enumerate(blk.transactions):
                    if not tx.payload_matches():
                        problems.append(f"block {i} tx {j}: payload does not match its hash")
                    if not self.registry.verify(tx.committer_id,
                                                tx.signing_material(), tx.signature):
                        problems.append(f"block {i} tx {j}: bad committer signature")

                if i > 0:
                    valid = sum(
                        1 for v, sig in blk.endorsements.items()
                        if self.registry.verify(v, blk.header_material(), sig)
                    )
                    if valid < max(1, self.registry.quorum_size):
                        problems.append(
                            f"block {i}: {valid} valid endorsements, "
                            f"quorum is {self.registry.quorum_size}")
        return (not problems), problems

    # ---------- audit queries ----------

    def transactions(self, zone_id: Optional[int] = None,
                     event_type: Optional[EventType] = None) -> List[Transaction]:
        out = []
        with self._lock:
            for blk in self.chain:
                for tx in blk.transactions:
                    if zone_id is not None and tx.zone_id != zone_id:
                        continue
                    if event_type is not None and tx.event_type != event_type.value:
                        continue
                    out.append(tx)
        return out

    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            counts: Dict[str, int] = {}
            total = 0
            for blk in self.chain:
                for tx in blk.transactions:
                    counts[tx.event_type] = counts.get(tx.event_type, 0) + 1
                    total += 1
            ok, problems = self.verify_chain()
            return {
                "blocks": len(self.chain),
                "committed_transactions": total,
                "pending_transactions": len(self.pending),
                "rejected_blocks": self._rejected,
                "events_by_type": counts,
                "validators": self.registry.size,
                "quorum_size": self.registry.quorum_size,
                "fault_tolerance": self.registry.fault_tolerance,
                "chain_valid": ok,
                "integrity_problems": problems[:5],
                "head_hash": self.chain[-1].block_hash if self.chain else None,
            }
