"""Experiment A: NN heuristic vs stronger route optimizers (Reviewer 1, comment 2)."""
import math, random, time, json, sys
import numpy as np
from core import BinSimulator, RouteOptimizer, path_length, _d

START = (50.0, 50.0)

# ---------- optimizers, all operating on a list of (x,y) points ----------

def opt_sequential(pts, start=START, rng=None):
    return list(range(len(pts)))

def opt_nn(pts, start=START, rng=None):
    n = len(pts); unvisited = set(range(n)); order = []; cur = start
    while unvisited:
        j = min(unvisited, key=lambda k: _d(cur[0], cur[1], pts[k][0], pts[k][1]))
        order.append(j); unvisited.discard(j); cur = pts[j]
    return order

def _tour_len(order, pts, start=START):
    return path_length(start, [pts[i] for i in order])

def opt_two_opt(pts, start=START, rng=None, init=None):
    """NN seed followed by 2-opt local search to a local optimum (open path)."""
    order = init if init is not None else opt_nn(pts, start)
    n = len(order)
    if n < 3:
        return order
    best = _tour_len(order, pts, start)
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                cand = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                L = _tour_len(cand, pts, start)
                if L < best - 1e-12:
                    order, best, improved = cand, L, True
    return order

def opt_or_opt(pts, start=START, rng=None):
    """2-opt to convergence, then Or-opt segment relocation (segments of 1-3)."""
    order = opt_two_opt(pts, start)
    n = len(order)
    if n < 4:
        return order
    best = _tour_len(order, pts, start)
    improved = True
    while improved:
        improved = False
        for seglen in (1, 2, 3):
            for i in range(0, n - seglen + 1):
                seg = order[i:i + seglen]
                rest = order[:i] + order[i + seglen:]
                for k in range(len(rest) + 1):
                    if k == i:
                        continue
                    cand = rest[:k] + seg + rest[k:]
                    L = _tour_len(cand, pts, start)
                    if L < best - 1e-12:
                        order, best, improved = cand, L, True
                        break
                if improved:
                    break
            if improved:
                break
    return order

def opt_ga(pts, start=START, rng=None, pop_size=60, generations=200,
           mutation_rate=0.2, elite=4):
    """Order-crossover genetic algorithm, NN-seeded population."""
    rng = rng or random.Random(0)
    n = len(pts)
    if n < 4:
        return opt_nn(pts, start)
    base = opt_nn(pts, start)
    pop = [base[:]]
    for _ in range(pop_size - 1):
        c = base[:]
        rng.shuffle(c)
        pop.append(c)

    def fit(o):
        return _tour_len(o, pts, start)

    for _ in range(generations):
        pop.sort(key=fit)
        newpop = pop[:elite]
        while len(newpop) < pop_size:
            p1 = min(rng.sample(pop, 3), key=fit)
            p2 = min(rng.sample(pop, 3), key=fit)
            a, b = sorted(rng.sample(range(n), 2))
            child = [None] * n
            child[a:b + 1] = p1[a:b + 1]
            taken = set(p1[a:b + 1])
            fill = [g for g in p2 if g not in taken]
            idx = 0
            for i in range(n):
                if child[i] is None:
                    child[i] = fill[idx]; idx += 1
            if rng.random() < mutation_rate:
                i, j = rng.sample(range(n), 2)
                child[i], child[j] = child[j], child[i]
            newpop.append(child)
        pop = newpop
    return min(pop, key=fit)

def opt_exact(pts, start=START, rng=None):
    """Held-Karp exact shortest open Hamiltonian path from a fixed start."""
    n = len(pts)
    if n == 0:
        return []
    if n > 16:
        raise ValueError("exact solver capped at 16 nodes")
    D = [[_d(pts[i][0], pts[i][1], pts[j][0], pts[j][1]) for j in range(n)] for i in range(n)]
    D0 = [_d(start[0], start[1], pts[j][0], pts[j][1]) for j in range(n)]
    size = 1 << n
    INF = float("inf")
    dp = [[INF] * n for _ in range(size)]
    par = [[-1] * n for _ in range(size)]
    for j in range(n):
        dp[1 << j][j] = D0[j]
    for mask in range(size):
        row = dp[mask]
        for j in range(n):
            cj = row[j]
            if cj == INF or not (mask >> j) & 1:
                continue
            Dj = D[j]
            for k in range(n):
                if (mask >> k) & 1:
                    continue
                nm = mask | (1 << k)
                v = cj + Dj[k]
                if v < dp[nm][k]:
                    dp[nm][k] = v
                    par[nm][k] = j
    full = size - 1
    end = min(range(n), key=lambda j: dp[full][j])
    order = []
    mask, j = full, end
    while j != -1:
        order.append(j)
        pj = par[mask][j]
        mask ^= (1 << j)
        j = pj
    return order[::-1]


ALGOS = [
    ("Sequential (fixed order)", opt_sequential),
    ("Nearest Neighbour", opt_nn),
    ("NN + 2-opt", opt_two_opt),
    ("NN + 2-opt + Or-opt", opt_or_opt),
    ("Genetic algorithm", opt_ga),
    ("Exact (Held-Karp)", opt_exact),
]

def main():
    n_runs, zones, bpz, steps = 10, 3, 15, 9
    optimizer = RouteOptimizer()
    rows = []
    zone_sizes = []
    for run in range(n_runs):
        sim = BinSimulator(zones, bpz, seed=1000 + run)
        for t in range(steps):
            sim.step(t)
        for z in range(1, zones + 1):
            ob = optimizer.overflowing(sim.bins_by_zone(z))
            pts = [(b.x, b.y) for b in ob]
            zone_sizes.append(len(pts))
            if not pts:
                continue
            rec = {"run": run, "zone": z, "n_bins": len(pts)}
            for name, fn in ALGOS:
                if name.startswith("Exact") and len(pts) > 16:
                    rec[name] = None; rec[name + "__ms"] = None
                    continue
                rng = random.Random(7000 + run * 10 + z)
                t0 = time.perf_counter()
                order = fn(pts, START, rng)
                ms = (time.perf_counter() - t0) * 1000
                rec[name] = _tour_len(order, pts, START)
                rec[name + "__ms"] = ms
            rows.append(rec)

    out = {"zone_overflow_sizes": zone_sizes, "rows": rows}
    with open("exp_a_routing.json", "w") as fh:
        json.dump(out, fh, indent=1)

    print("zone-instances evaluated:", len(rows))
    nz = [z for z in zone_sizes if z]
    print("overflowing bins per zone: min %d max %d mean %.2f" % (min(nz), max(nz), np.mean(nz)))
    names = [n for n, _ in ALGOS]
    valid = [r for r in rows if r.get("Exact (Held-Karp)") is not None]
    print("exact solved on %d/%d zone-instances" % (len(valid), len(rows)))
    print()
    hdr = "%-26s %10s %8s %11s %10s %9s" % ("algorithm", "mean dist", "vs seq", "gap vs opt", "mean ms", "max ms")
    print(hdr)
    for nm in names:
        d = np.array([r[nm] for r in rows if r[nm] is not None])
        ms = np.array([r[nm + "__ms"] for r in rows if r[nm + "__ms"] is not None])
        seq = np.array([r["Sequential (fixed order)"] for r in rows if r[nm] is not None])
        gaps = [100 * (r[nm] - r["Exact (Held-Karp)"]) / r["Exact (Held-Karp)"]
                for r in valid if r[nm] is not None]
        print("%-26s %10.2f %7.1f%% %10.2f%% %10.3f %9.3f" %
              (nm, d.mean(), 100 * (1 - d.sum() / seq.sum()), np.mean(gaps), ms.mean(), ms.max()))
        print("      gap max %.2f%%  |  worst-case per-zone gap" % (max(gaps) if gaps else 0))

    print("\nPer-run system-wide distance reduction vs sequential baseline:")
    for nm in names[1:]:
        red = []
        for run in range(n_runs):
            rr = [r for r in rows if r["run"] == run and r[nm] is not None]
            if len(rr) != zones:
                continue
            s = sum(r["Sequential (fixed order)"] for r in rr)
            a = sum(r[nm] for r in rr)
            red.append(100 * (s - a) / s)
        print("  %-26s mean %5.1f%%  range %5.1f-%5.1f%%  (n=%d)" %
              (nm, np.mean(red), np.min(red), np.max(red), len(red)))

if __name__ == "__main__":
    main()
