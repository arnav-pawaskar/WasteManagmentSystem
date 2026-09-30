"""Experiment C: blockchain overhead of contracts/ledger.py.

Measures commit latency, throughput, storage growth, verification cost and CPU time
(Reviewer 1, comment 4). Uses the REAL ledger implementation from the repository.
"""
import sys, os, time, json, gc
import numpy as np

sys.path.insert(0, r"C:\projects\WasteManagmentSystem")
from contracts.ledger import (PermissionedLedger, ValidatorRegistry, EventType,
                              canonical_json)


def make_ledger(n_validators=4, block_size=8):
    reg = ValidatorRegistry()
    for i in range(n_validators):
        reg.register(f"fog_{i+1}")
    return PermissionedLedger(reg, block_size=block_size), reg


PAYLOAD = {"bin_id": "bin_1_7", "fill_level": 93.4, "truck_id": "truck_1",
           "lat": 19.1071, "lon": 72.8370, "serviced_at": "2026-03-01T09:14:22"}


def measure_submit_latency(n=5000, n_validators=4, block_size=8):
    """End-to-end submit() latency: hash + sign + queue (+ seal when block fills)."""
    ledger, reg = make_ledger(n_validators, block_size)
    lat = []
    for i in range(n):
        t0 = time.perf_counter()
        ledger.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")
        lat.append((time.perf_counter() - t0) * 1000)
    return np.array(lat), ledger


def measure_seal_latency(n_validators, block_size, n_blocks=200):
    """Latency of sealing one full block: propose + endorse x n + commit."""
    ledger, reg = make_ledger(n_validators, block_size)
    lat = []
    for b in range(n_blocks):
        for i in range(block_size - 1):
            ledger.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")
        t0 = time.perf_counter()
        ledger.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")   # triggers seal
        lat.append((time.perf_counter() - t0) * 1000)
    return np.array(lat)


def chain_bytes(ledger):
    """Serialized on-disk footprint of the whole chain (canonical JSON)."""
    from dataclasses import asdict
    total = 0
    for blk in ledger.chain:
        total += len(canonical_json({
            "index": blk.index, "prev_hash": blk.prev_hash,
            "timestamp": blk.timestamp, "merkle_root": blk.merkle_root,
            "block_hash": blk.block_hash, "endorsements": blk.endorsements,
            "transactions": [asdict(t) for t in blk.transactions],
        }).encode("utf-8"))
    return total


def main():
    out = {}
    print("=" * 88)
    print("C1  TRANSACTION COMMIT LATENCY AND THROUGHPUT  (n=4 validators, block=8 tx)")
    print("=" * 88)
    lat, ledger = measure_submit_latency(5000, 4, 8)
    print("  submit() latency  mean %.4f ms | median %.4f | p95 %.4f | max %.4f ms" %
          (lat.mean(), np.median(lat), np.percentile(lat, 95), lat.max()))
    # separate the two populations: plain queue vs the submit that seals a block
    sealing = lat[7::8]
    plain = np.array([v for i, v in enumerate(lat) if i % 8 != 7])
    print("  non-sealing submit : mean %.4f ms (n=%d)" % (plain.mean(), len(plain)))
    print("  sealing submit     : mean %.4f ms (n=%d)" % (sealing.mean(), len(sealing)))
    total_s = lat.sum() / 1000
    print("  sustained throughput: %.0f tx/s  (%d tx in %.3f s of CPU)" %
          (5000 / total_s, 5000, total_s))
    out["c1"] = {"mean_ms": float(lat.mean()), "median_ms": float(np.median(lat)),
                 "p95_ms": float(np.percentile(lat, 95)), "max_ms": float(lat.max()),
                 "plain_ms": float(plain.mean()), "seal_ms": float(sealing.mean()),
                 "throughput_tps": float(5000 / total_s)}

    print()
    print("=" * 88)
    print("C2  BLOCK SEAL LATENCY vs VALIDATOR-SET SIZE  (block = 8 tx)")
    print("=" * 88)
    print("  %-12s %-8s %-8s %12s %12s" % ("validators", "f", "quorum", "mean ms", "p95 ms"))
    rows = []
    for nv in [4, 7, 10, 13, 16]:
        reg = ValidatorRegistry()
        for i in range(nv):
            reg.register(f"fog_{i+1}")
        L = PermissionedLedger(reg, block_size=8)
        sl = measure_seal_latency(nv, 8, n_blocks=200)
        rows.append({"validators": nv, "f": reg.fault_tolerance,
                     "quorum": reg.quorum_size, "mean_ms": float(sl.mean()),
                     "p95_ms": float(np.percentile(sl, 95))})
        print("  %-12d %-8d %-8d %12.4f %12.4f" %
              (nv, reg.fault_tolerance, reg.quorum_size, sl.mean(), np.percentile(sl, 95)))
    out["c2"] = rows

    print()
    print("=" * 88)
    print("C3  BLOCK SEAL LATENCY vs BLOCK SIZE  (4 validators)")
    print("=" * 88)
    print("  %-12s %12s %12s %16s" % ("tx/block", "mean ms", "p95 ms", "ms per tx"))
    rows = []
    for bs in [1, 2, 4, 8, 16, 32, 64]:
        sl = measure_seal_latency(4, bs, n_blocks=max(50, 400 // bs))
        rows.append({"block_size": bs, "mean_ms": float(sl.mean()),
                     "p95_ms": float(np.percentile(sl, 95)),
                     "ms_per_tx": float(sl.mean() / bs)})
        print("  %-12d %12.4f %12.4f %16.4f" %
              (bs, sl.mean(), np.percentile(sl, 95), sl.mean() / bs))
    out["c3"] = rows

    print()
    print("=" * 88)
    print("C4  STORAGE GROWTH  (4 validators, block = 8 tx, canonical-JSON encoding)")
    print("=" * 88)
    print("  %-10s %-10s %14s %14s" % ("tx", "blocks", "chain bytes", "bytes/tx"))
    rows = []
    for n in [80, 400, 800, 4000, 8000]:
        L, reg = make_ledger(4, 8)
        for i in range(n):
            L.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")
        L.flush("fog_1")
        b = chain_bytes(L)
        rows.append({"tx": n, "blocks": len(L.chain), "bytes": b, "bytes_per_tx": b / n})
        print("  %-10d %-10d %14d %14.1f" % (n, len(L.chain), b, b / n))
    out["c4"] = rows
    bpt = rows[-1]["bytes_per_tx"]

    print()
    print("  Marginal cost from the two largest points: %.1f B/tx" %
          ((rows[-1]["bytes"] - rows[-2]["bytes"]) / (rows[-1]["tx"] - rows[-2]["tx"])))

    print()
    print("=" * 88)
    print("C5  CHAIN VERIFICATION COST  (full audit, verify_chain())")
    print("=" * 88)
    print("  %-10s %-10s %14s %16s" % ("tx", "blocks", "verify ms", "us per tx"))
    rows = []
    for n in [80, 400, 800, 4000, 8000]:
        L, reg = make_ledger(4, 8)
        for i in range(n):
            L.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")
        L.flush("fog_1")
        ts = []
        for _ in range(3):
            t0 = time.perf_counter()
            ok, probs = L.verify_chain()
            ts.append((time.perf_counter() - t0) * 1000)
        assert ok, probs[:3]
        rows.append({"tx": n, "blocks": len(L.chain), "verify_ms": float(np.median(ts)),
                     "us_per_tx": float(np.median(ts) * 1000 / n)})
        print("  %-10d %-10d %14.2f %16.2f" %
              (n, len(L.chain), np.median(ts), np.median(ts) * 1000 / n))
    out["c5"] = rows

    print()
    print("=" * 88)
    print("C6  TAMPER DETECTION  (does the audit actually catch modification?)")
    print("=" * 88)
    L, reg = make_ledger(4, 8)
    for i in range(80):
        L.submit(EventType.BIN_SERVICED, 1, dict(PAYLOAD, seq=i), "fog_1")
    L.flush("fog_1")
    ok, _ = L.verify_chain()
    print("  clean chain verifies      :", ok)
    # mutate a committed payload in place
    L.chain[3].transactions[2].payload["fill_level"] = 12.0
    ok2, probs = L.verify_chain()
    print("  after payload mutation    :", ok2, "|", probs[0] if probs else "-")
    out["c6"] = {"clean": ok, "tampered": ok2, "detected": (not ok2)}

    print()
    print("=" * 88)
    print("C7  PROJECTED LOAD FOR A MUNICIPAL DEPLOYMENT")
    print("=" * 88)
    for bins, daily in [(1000, 1), (10000, 1), (100000, 1)]:
        # one BIN_SERVICED per collection + one ROUTE_COMPLETED per truck-route
        tx_day = bins * daily
        print("  %7d bins, %d collection/day -> %8d tx/day = %.3f tx/s ; "
              "storage %.2f MB/day, %.2f GB/year" %
              (bins, daily, tx_day, tx_day / 86400,
               tx_day * bpt / 1e6, tx_day * 365 * bpt / 1e9))
    out["c7"] = {"bytes_per_tx": bpt}

    json.dump(out, open("exp_c_ledger.json", "w"), indent=1)
    print("\nwritten exp_c_ledger.json")


if __name__ == "__main__":
    main()
