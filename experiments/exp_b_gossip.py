"""Experiment B: gossip + spillover under varying load, message loss and node failure.

Mirrors modules/inter_fog_comm/{gossip,spillover}.py:
  * rumour-mongering gossip: each round push local ZoneState to `fanout` random peers
  * spillover: overloaded node picks the least-loaded peer FROM ITS GOSSIP VIEW
    (which may be stale), receiver applies a point-in-time admission check
  * message loss and node failure are applied per message / per node
"""
import random, json, statistics
import numpy as np
from core import BinSimulator

TAU_DEFAULT = 10


class FogNet:
    def __init__(self, zones, bins_per_zone, seed, tau=TAU_DEFAULT, fanout=3,
                 loss=0.0, failed=(), hot_zone=1, hot_mult=1.6, max_move=3):
        self.zones = zones
        self.tau = tau
        self.fanout = fanout
        self.loss = loss
        self.failed = set(failed)
        self.hot_zone = hot_zone
        self.hot_mult = hot_mult
        self.max_move = max_move
        self.sim = BinSimulator(zones, bins_per_zone, seed=seed)
        self.net_rng = random.Random(seed + 777)
        # gossip view: zone -> believed active_bins of every peer (None = unknown)
        self.view = {z: {} for z in range(1, zones + 1)}
        self.transfers = []
        self.requests = 0
        self.rejected = 0
        self.lost_msgs = 0
        self.view_error = []          # mean |believed - true| per round, live nodes only

    def true_counts(self):
        return {z: sum(1 for b in self.sim.bins_by_zone(z) if b.is_overflowing())
                for z in range(1, self.zones + 1)}

    def _deliver(self):
        """True if a message gets through this hop."""
        if self.net_rng.random() < self.loss:
            self.lost_msgs += 1
            return False
        return True

    def gossip_round(self):
        counts = self.true_counts()
        live = [z for z in range(1, self.zones + 1) if z not in self.failed]
        for z in live:
            peers = [p for p in live if p != z]
            if not peers:
                continue
            targets = (peers if len(peers) <= self.fanout
                       else self.net_rng.sample(peers, self.fanout))
            for t in targets:
                if self._deliver():
                    self.view[t][z] = counts[z]
        # accuracy of each live node's view of its live peers
        errs = []
        for z in live:
            for p in live:
                if p == z:
                    continue
                believed = self.view[z].get(p)
                if believed is not None:
                    errs.append(abs(believed - counts[p]))
        if errs:
            self.view_error.append(float(np.mean(errs)))

    def spillover_round(self, t):
        counts = self.true_counts()
        live = [z for z in range(1, self.zones + 1) if z not in self.failed]
        for z in live:
            if counts[z] <= self.tau:
                continue
            # candidates ranked by BELIEVED load (gossip view), not ground truth
            cands = [(p, v) for p, v in self.view[z].items()
                     if p in live and p != z and v < self.tau]
            if not cands:
                continue
            cands.sort(key=lambda kv: kv[1])
            for peer, believed in cands:
                self.requests += 1
                if not self._deliver():          # request lost
                    break
                true_peer = counts[peer]
                move = max(0, min(self.max_move, counts[z] - self.tau,
                                  self.tau - true_peer))
                if move == 0:                    # receiver-side admission check fails
                    self.rejected += 1
                    continue
                if not self._deliver():          # response lost -> sender keeps bins
                    break
                movers = sorted([b for b in self.sim.bins_by_zone(z) if b.is_overflowing()],
                                key=lambda b: b.fill_level)[:move]
                for b in movers:
                    b.zone_id = peer
                self.transfers.append({"t": t, "from": z, "to": peer, "n_bins": len(movers)})
                counts = self.true_counts()
                break

    def run(self, steps=14, enable_spillover=True):
        for t in range(steps):
            self.sim.step(t, hot_zone=self.hot_zone, hot_multiplier=self.hot_mult)
            self.gossip_round()
            if enable_spillover:
                self.spillover_round(t)
        return self.true_counts()


def metrics(counts, tau, failed=()):
    live = {z: c for z, c in counts.items() if z not in failed}
    vals = list(live.values())
    return {
        "max_load": max(vals),
        "total": sum(counts.values()),
        "std": float(statistics.pstdev(vals)) if len(vals) > 1 else 0.0,
        "above_tau": sum(1 for v in vals if v > tau),
        "n_zones": len(vals),
    }


def sweep_load():
    print("=" * 96)
    print("B1  LOAD SWEEP  (3 zones x 15 bins, tau=10, no loss, no failure, 14 steps)")
    print("=" * 96)
    print("%-8s | %-28s | %-28s | %s" % ("hot", "WITHOUT spillover", "WITH spillover", ""))
    print("%-8s | %5s %5s %6s %5s | %5s %5s %6s %5s | %s" %
          ("mult", "max", "tot", "std", ">tau", "max", "tot", "std", ">tau", "transfers"))
    rows = []
    for hm in [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.4]:
        a = FogNet(3, 15, seed=3000, hot_mult=hm)
        ca = a.run(enable_spillover=False)
        b = FogNet(3, 15, seed=3000, hot_mult=hm)
        cb = b.run(enable_spillover=True)
        ma, mb = metrics(ca, 10), metrics(cb, 10)
        rows.append({"hot_mult": hm, "without": ma, "with": mb,
                     "transfers": len(b.transfers)})
        print("%-8.1f | %5d %5d %6.2f %5d | %5d %5d %6.2f %5d | %d" %
              (hm, ma["max_load"], ma["total"], ma["std"], ma["above_tau"],
               mb["max_load"], mb["total"], mb["std"], mb["above_tau"], len(b.transfers)))
    return rows


def sweep_loss():
    print()
    print("=" * 96)
    print("B2  MESSAGE-LOSS SWEEP  (3 zones, hot=1.6, tau=10; 20 seeds per point)")
    print("=" * 96)
    print("%-6s %8s %8s %8s %8s %8s %10s" %
          ("loss", "max", "std", ">tau", "transf", "reqs", "view_err"))
    rows = []
    for loss in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7]:
        mx, sd, at, tr, rq, ve = [], [], [], [], [], []
        for s in range(20):
            n = FogNet(3, 15, seed=3000 + s, loss=loss)
            c = n.run(enable_spillover=True)
            m = metrics(c, 10)
            mx.append(m["max_load"]); sd.append(m["std"]); at.append(m["above_tau"])
            tr.append(len(n.transfers)); rq.append(n.requests)
            ve.append(np.mean(n.view_error) if n.view_error else float("nan"))
        rows.append({"loss": loss, "max": float(np.mean(mx)), "std": float(np.mean(sd)),
                     "above_tau": float(np.mean(at)), "transfers": float(np.mean(tr)),
                     "requests": float(np.mean(rq)), "view_err": float(np.nanmean(ve))})
        print("%-6.1f %8.2f %8.2f %8.2f %8.2f %8.2f %10.3f" %
              (loss, np.mean(mx), np.mean(sd), np.mean(at), np.mean(tr),
               np.mean(rq), np.nanmean(ve)))
    return rows


def sweep_failure():
    print()
    print("=" * 96)
    print("B3  NODE-FAILURE SWEEP  (5 zones x 15 bins, hot=1.6, tau=10; 20 seeds)")
    print("=" * 96)
    print("%-10s %8s %8s %8s %8s %10s" %
          ("failed", "max", "std", ">tau", "transf", "live_zones"))
    rows = []
    for nf in [0, 1, 2, 3]:
        failed = tuple(range(2, 2 + nf))          # never fail the hot zone (1)
        mx, sd, at, tr = [], [], [], []
        for s in range(20):
            n = FogNet(5, 15, seed=3000 + s, failed=failed)
            c = n.run(enable_spillover=True)
            m = metrics(c, 10, failed=failed)
            mx.append(m["max_load"]); sd.append(m["std"]); at.append(m["above_tau"])
            tr.append(len(n.transfers))
        rows.append({"failed": nf, "max": float(np.mean(mx)), "std": float(np.mean(sd)),
                     "above_tau": float(np.mean(at)), "transfers": float(np.mean(tr)),
                     "live": 5 - nf})
        print("%-10d %8.2f %8.2f %8.2f %8.2f %10d" %
              (nf, np.mean(mx), np.mean(sd), np.mean(at), np.mean(tr), 5 - nf))
    return rows


def sweep_tau():
    print()
    print("=" * 96)
    print("B4  THRESHOLD SWEEP  (3 zones, hot=1.6, no loss; 20 seeds)")
    print("=" * 96)
    print("%-6s %10s %10s %10s %10s %10s" %
          ("tau", "max(no sp)", "max(sp)", "std(no sp)", "std(sp)", ">tau(sp)"))
    rows = []
    for tau in [8, 10, 12, 14]:
        mxa, mxb, sda, sdb, atb, trs = [], [], [], [], [], []
        for s in range(20):
            a = FogNet(3, 15, seed=3000 + s, tau=tau)
            ca = a.run(enable_spillover=False)
            b = FogNet(3, 15, seed=3000 + s, tau=tau)
            cb = b.run(enable_spillover=True)
            ma, mb = metrics(ca, tau), metrics(cb, tau)
            mxa.append(ma["max_load"]); mxb.append(mb["max_load"])
            sda.append(ma["std"]); sdb.append(mb["std"])
            atb.append(mb["above_tau"]); trs.append(len(b.transfers))
        rows.append({"tau": tau, "max_no": float(np.mean(mxa)), "max_sp": float(np.mean(mxb)),
                     "std_no": float(np.mean(sda)), "std_sp": float(np.mean(sdb)),
                     "above_tau": float(np.mean(atb)), "transfers": float(np.mean(trs))})
        print("%-6d %10.2f %10.2f %10.2f %10.2f %10.2f" %
              (tau, np.mean(mxa), np.mean(mxb), np.mean(sda), np.mean(sdb), np.mean(atb)))
    return rows


def gossip_convergence():
    """Rounds for a single new state to reach every live node, vs N and loss."""
    print()
    print("=" * 96)
    print("B5  GOSSIP CONVERGENCE  (rounds until all peers hold the newest state;")
    print("    fanout=3, 2000 trials per point; 'inf' runs excluded and counted)")
    print("=" * 96)
    print("%-6s %-6s %10s %10s %10s %10s" % ("N", "loss", "mean", "p95", "max", "fail%"))
    rows = []
    for N in [3, 5, 10, 20, 50]:
        for loss in [0.0, 0.2, 0.5]:
            res, fails = [], 0
            for trial in range(2000):
                rng = random.Random(90000 + N * 1000 + int(loss * 100) * 7 + trial)
                informed = {1}
                rounds = 0
                while len(informed) < N and rounds < 200:
                    rounds += 1
                    newly = set()
                    for z in list(informed):
                        peers = [p for p in range(1, N + 1) if p != z]
                        tg = peers if len(peers) <= 3 else rng.sample(peers, 3)
                        for t in tg:
                            if rng.random() >= loss:
                                newly.add(t)
                    informed |= newly
                if len(informed) < N:
                    fails += 1
                else:
                    res.append(rounds)
            if res:
                rows.append({"N": N, "loss": loss, "mean": float(np.mean(res)),
                             "p95": float(np.percentile(res, 95)), "max": int(max(res)),
                             "fail_pct": 100.0 * fails / 2000})
                print("%-6d %-6.1f %10.2f %10.1f %10d %10.2f" %
                      (N, loss, np.mean(res), np.percentile(res, 95), max(res),
                       100.0 * fails / 2000))
    return rows


if __name__ == "__main__":
    out = {}
    out["load"] = sweep_load()
    out["loss"] = sweep_loss()
    out["failure"] = sweep_failure()
    out["tau"] = sweep_tau()
    out["convergence"] = gossip_convergence()
    json.dump(out, open("exp_b_gossip.json", "w"), indent=1)
    print("\nwritten exp_b_gossip.json")
