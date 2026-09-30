"""Experiment A2: how each optimizer's cost scales with overflowing bins per zone."""
import random, time, json
import numpy as np
from core import _d
from exp_a_routing import (opt_nn, opt_two_opt, opt_or_opt, opt_ga, opt_exact,
                           _tour_len, START)

ALGOS = [("Nearest Neighbour", opt_nn),
         ("NN + 2-opt", opt_two_opt),
         ("NN + 2-opt + Or-opt", opt_or_opt),
         ("Genetic algorithm", opt_ga),
         ("Exact (Held-Karp)", opt_exact)]

EXACT_CAP = 16   # beyond this Held-Karp is not attempted

def main():
    sizes = [5, 8, 10, 12, 14, 16, 20, 30, 50]
    trials = 5
    rows = []
    for n in sizes:
        for name, fn in ALGOS:
            if name.startswith("Exact") and n > EXACT_CAP:
                continue
            ts, ds = [], []
            for k in range(trials):
                rng = random.Random(50000 + n * 100 + k)
                pts = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
                r2 = random.Random(60000 + n * 100 + k)
                t0 = time.perf_counter()
                order = fn(pts, START, r2)
                ts.append((time.perf_counter() - t0) * 1000)
                ds.append(_tour_len(order, pts, START))
            rows.append({"n": n, "algo": name, "ms_median": float(np.median(ts)),
                         "ms_mean": float(np.mean(ts)), "dist_mean": float(np.mean(ds))})
            print("n=%-3d %-24s median %10.3f ms   mean dist %7.2f" %
                  (n, name, np.median(ts), np.mean(ds)))
        print()
    json.dump(rows, open("exp_a2_scaling.json", "w"), indent=1)

    print("\n--- projected Held-Karp cost (O(n^2 2^n)) ---")
    ex = [r for r in rows if r["algo"].startswith("Exact")]
    if len(ex) >= 2:
        ref = ex[-1]
        for n in (16, 18, 20, 22, 25):
            scale = (n ** 2 * 2 ** n) / (ref["n"] ** 2 * 2 ** ref["n"])
            print("  n=%-3d projected %12.1f ms  (%.2f s)" %
                  (n, ref["ms_median"] * scale, ref["ms_median"] * scale / 1000))

if __name__ == "__main__":
    main()
