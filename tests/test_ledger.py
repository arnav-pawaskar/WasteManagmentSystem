#!/usr/bin/env python3
"""
Test suite for the permissioned ledger (Section IV-D of the paper).
"""

import sys
import os
import unittest
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.ledger import (
    EventType, PermissionedLedger, ValidatorRegistry,
    Transaction, canonical_json, sha256_hex, merkle_root,
)


def build(n_validators=4, block_size=8):
    reg = ValidatorRegistry()
    for i in range(1, n_validators + 1):
        reg.register(str(i))
    return reg, PermissionedLedger(reg, block_size=block_size)


class TestValidatorRegistry(unittest.TestCase):

    def test_quorum_sizing_follows_pbft(self):
        for n, f, q in [(1, 0, 1), (3, 0, 1), (4, 1, 3), (7, 2, 5), (10, 3, 7)]:
            reg = ValidatorRegistry()
            for i in range(n):
                reg.register(f"n{i}")
            self.assertEqual(reg.fault_tolerance, f, f"n={n}")
            self.assertEqual(reg.quorum_size, q, f"n={n}")

    def test_signature_roundtrip_and_rejection(self):
        reg, _ = build()
        sig = reg.sign("1", "hello")
        self.assertTrue(reg.verify("1", "hello", sig))
        self.assertFalse(reg.verify("1", "tampered", sig))
        self.assertFalse(reg.verify("2", "hello", sig))
        self.assertFalse(reg.verify("unknown", "hello", sig))

    def test_unregistered_node_cannot_sign(self):
        reg, _ = build()
        with self.assertRaises(KeyError):
            reg.sign("nope", "msg")


class TestLedgerCommit(unittest.TestCase):

    def test_genesis_exists_and_verifies(self):
        _, ledger = build()
        self.assertEqual(len(ledger.chain), 1)
        self.assertEqual(ledger.chain[0].prev_hash, PermissionedLedger.GENESIS_PREV)
        ok, problems = ledger.verify_chain()
        self.assertTrue(ok, problems)

    def test_submit_signs_and_hashes_payload(self):
        _, ledger = build()
        tx = ledger.submit(EventType.BIN_SERVICED, 1,
                           {"bin_id": "bin_1_3", "fill_level": 91.2}, "1")
        self.assertEqual(tx.event_type, "BIN_SERVICED")
        self.assertEqual(tx.zone_id, 1)
        self.assertTrue(tx.payload_matches())
        self.assertEqual(tx.payload_hash,
                         sha256_hex(canonical_json({"bin_id": "bin_1_3", "fill_level": 91.2})))

    def test_auto_seals_at_block_size(self):
        _, ledger = build(block_size=4)
        for i in range(4):
            ledger.submit(EventType.BIN_SERVICED, 1, {"bin_id": f"b{i}"}, "1")
        self.assertEqual(len(ledger.chain), 2)
        self.assertEqual(len(ledger.pending), 0)
        ok, problems = ledger.verify_chain()
        self.assertTrue(ok, problems)

    def test_chain_linkage_across_many_blocks(self):
        _, ledger = build(block_size=2)
        for i in range(10):
            ledger.submit(EventType.ZONE_SNAPSHOT, (i % 3) + 1, {"n": i}, "1")
        self.assertEqual(len(ledger.chain), 6)          # genesis + 5
        for i in range(1, len(ledger.chain)):
            self.assertEqual(ledger.chain[i].prev_hash, ledger.chain[i - 1].block_hash)
        ok, problems = ledger.verify_chain()
        self.assertTrue(ok, problems)

    def test_flush_seals_remainder(self):
        _, ledger = build(block_size=100)
        ledger.submit(EventType.ROUTE_COMPLETED, 2, {"truck": "t1"}, "2")
        self.assertEqual(len(ledger.chain), 1)
        ledger.flush("2")
        self.assertEqual(len(ledger.chain), 2)
        self.assertEqual(len(ledger.pending), 0)

    def test_block_below_quorum_is_rejected(self):
        reg, ledger = build(n_validators=4)          # quorum = 3
        ledger.submit(EventType.BIN_SERVICED, 1, {"b": 1}, "1")
        blk = ledger.propose_block("1")              # proposer endorses -> 1 endorsement
        self.assertEqual(len(blk.endorsements), 1)
        self.assertFalse(ledger.commit_block(blk))
        ledger.endorse(blk, "2")
        self.assertFalse(ledger.commit_block(blk))   # 2 < 3
        ledger.endorse(blk, "3")
        self.assertTrue(ledger.commit_block(blk))    # 3 == quorum

    def test_block_with_wrong_parent_is_rejected(self):
        _, ledger = build(n_validators=1, block_size=100)
        ledger.submit(EventType.BIN_SERVICED, 1, {"b": 1}, "1")
        blk = ledger.propose_block("1")
        blk.prev_hash = "f" * 64
        blk.block_hash = blk.recompute_hash()
        self.assertFalse(ledger.commit_block(blk))


class TestTamperDetection(unittest.TestCase):
    """The append-only guarantee is only worth what verify_chain() can catch."""

    def _sealed(self):
        reg, ledger = build(n_validators=4, block_size=2)
        ledger.submit(EventType.BIN_SERVICED, 1, {"bin_id": "bin_1_1"}, "1")
        ledger.submit(EventType.BIN_SERVICED, 1, {"bin_id": "bin_1_2"}, "1")
        ok, _ = ledger.verify_chain()
        self.assertTrue(ok)
        return reg, ledger

    def test_detects_payload_tampering(self):
        _, ledger = self._sealed()
        ledger.chain[1].transactions[0].payload["bin_id"] = "bin_9_9"
        ok, problems = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("payload" in p for p in problems), problems)

    def test_detects_forged_transaction_signature(self):
        _, ledger = self._sealed()
        old = ledger.chain[1].transactions[0]
        forged = Transaction(
            event_type=old.event_type, zone_id=99, timestamp=old.timestamp,
            payload=old.payload, payload_hash=old.payload_hash,
            committer_id=old.committer_id, signature=old.signature,
        )
        ledger.chain[1].transactions[0] = forged
        ok, problems = ledger.verify_chain()
        self.assertFalse(ok)

    def test_detects_broken_linkage(self):
        _, ledger = self._sealed()
        ledger.chain[1].prev_hash = "a" * 64
        ledger.chain[1].block_hash = ledger.chain[1].recompute_hash()
        ok, problems = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("linkage" in p for p in problems), problems)

    def test_detects_transaction_deletion(self):
        _, ledger = self._sealed()
        del ledger.chain[1].transactions[0]
        ok, problems = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("Merkle" in p for p in problems), problems)

    def test_detects_stripped_endorsements(self):
        _, ledger = self._sealed()
        ledger.chain[1].endorsements = {}
        ok, problems = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertTrue(any("endorsement" in p for p in problems), problems)


class TestMerkleAndAudit(unittest.TestCase):

    def test_merkle_root_is_order_sensitive(self):
        a, b = sha256_hex("a"), sha256_hex("b")
        self.assertNotEqual(merkle_root([a, b]), merkle_root([b, a]))

    def test_merkle_handles_odd_counts(self):
        d = [sha256_hex(str(i)) for i in range(5)]
        self.assertEqual(len(merkle_root(d)), 64)

    def test_audit_filters_by_zone_and_type(self):
        _, ledger = build(block_size=100)
        ledger.submit(EventType.BIN_SERVICED, 1, {"b": 1}, "1")
        ledger.submit(EventType.BIN_SERVICED, 2, {"b": 2}, "2")
        ledger.submit(EventType.SPILLOVER_TRANSFER, 1, {"to": 2}, "1")
        ledger.flush("1")

        self.assertEqual(len(ledger.transactions()), 3)
        self.assertEqual(len(ledger.transactions(zone_id=1)), 2)
        self.assertEqual(len(ledger.transactions(event_type=EventType.BIN_SERVICED)), 2)
        self.assertEqual(
            len(ledger.transactions(zone_id=1, event_type=EventType.SPILLOVER_TRANSFER)), 1)

    def test_statistics_report_integrity(self):
        _, ledger = build(block_size=2)
        ledger.submit(EventType.ROUTE_COMPLETED, 1, {"t": "t1"}, "1")
        ledger.submit(EventType.BIN_SERVICED, 1, {"b": "b1"}, "1")
        stats = ledger.get_statistics()
        self.assertTrue(stats["chain_valid"])
        self.assertEqual(stats["committed_transactions"], 2)
        self.assertEqual(stats["events_by_type"]["ROUTE_COMPLETED"], 1)
        self.assertEqual(stats["blocks"], 2)


class TestDeterminism(unittest.TestCase):

    def test_canonical_json_is_key_order_independent(self):
        self.assertEqual(canonical_json({"a": 1, "b": 2}), canonical_json({"b": 2, "a": 1}))

    def test_same_payload_same_hash(self):
        p = {"zone": 3, "bins": ["b1", "b2"]}
        self.assertEqual(sha256_hex(canonical_json(p)),
                         sha256_hex(canonical_json(dict(reversed(list(p.items()))))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
