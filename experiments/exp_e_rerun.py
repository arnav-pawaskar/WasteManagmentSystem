"""Experiment E: re-run the paper's original Section V experiments on THIS machine,
so every timing in the paper comes from one consistent environment."""
import random, time, json, gc, tracemalloc, platform
import numpy as np
from core import BinSimulator, RouteOptimizer, BinTelemetry


def route_efficiency(n_runs=10, zones=3, bins_per_zone=15, sim_steps=9):
    opt = RouteOptimizer()
    nn_d, seq_d, nbins = [], [], []
    for run in range(n_runs):
        sim = BinSimulator(zones, bins_per_zone, seed=1000 + run)
        for t in range(sim_steps):
            sim.step(t)
        rn = rs = 0.0; nb = 0
        for z in range(1, zones + 1):
            zb = sim.bins_by_zone(z)
            r1 = opt.nearest_neighbour_route(zb, zone_id=z)
            r2 = opt.sequential_route(zb, zone_id=z)
            rn += r1.route_distance; rs += r2.route_distance; nb += len(r1.route_bins)
        nn_d.append(rn); seq_d.append(rs); nbins.append(nb)
    red = [100 * (s - n) / s for s, n in zip(seq_d, nn_d)]
    return {"mean_reduction": float(np.mean(red)), "min": float(np.min(red)),
            "max": float(np.max(red)), "total_overflow_bins": nbins}


def replanning_latency(n_events=50, bins_per_zone=20):
    opt = RouteOptimizer()
    lat = []
    for i in range(n_events):
        sim = BinSimulator(1, bins_per_zone, seed=2000 + i)
        for t in range(20):
            sim.step(t)
        zb = sim.bins_by_zone(1)
        _ = opt.nearest_neighbour_route(zb, zone_id=1)
        rng = random.Random(9000 + i)
        nb = BinTelemetry(f"bin_1_{bins_per_zone+1}", 1, rng.uniform(0, 100),
                          rng.uniform(0, 100), 92.0, 20)
        upd = zb + [nb]
        t0 = time.perf_counter()
        _ = opt.nearest_neighbour_route(upd, zone_id=1)
        lat.append((time.perf_counter() - t0) * 1000)
    a = np.array(lat)
    return {"mean": float(a.mean()), "median": float(np.median(a)),
            "max": float(a.max()), "std": float(a.std(ddof=1))}


def cycle_time_ms(zones, bpz, seed, steps=24, repeats=7):
    opt = RouteOptimizer()
    sim = BinSimulator(zones, bpz, seed=seed)
    for t in range(steps):
        sim.step(t)
    zb = [sim.bins_by_zone(z) for z in range(1, zones + 1)]
    s = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for z, b in enumerate(zb, start=1):
            opt.nearest_neighbour_route(b, zone_id=z)
        s.append((time.perf_counter() - t0) * 1000)
    return float(np.median(s))


def memory_kb(zones, bpz, seed, steps=24):
    opt = RouteOptimizer()
    gc.collect()
    tracemalloc.start()
    base, _ = tracemalloc.get_traced_memory()
    sim = BinSimulator(zones, bpz, seed=seed)
    for t in range(steps):
        sim.step(t)
    routes = [opt.nearest_neighbour_route(sim.bins_by_zone(z), zone_id=z)
              for z in range(1, zones + 1)]
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    r = (cur - base) / 1024
    del sim, routes
    return r


def scalability():
    rows = []
    for zones in (3, 4, 5):
        for bpz in (10, 15, 20):
            seed = 4000 + zones * 100 + bpz
            rows.append({"zones": zones, "bins_per_zone": bpz,
                         "total_bins": zones * bpz,
                         "cycle_time_ms": cycle_time_ms(zones, bpz, seed),
                         "memory_kb": memory_kb(zones, bpz, seed)})
    return rows


if __name__ == "__main__":
    print("machine:", platform.processor(), "|", platform.system(), platform.release(),
          "| Python", platform.python_version())
    print()
    r = route_efficiency()
    print("[V-A] NN vs sequential: mean %.1f%%  range %.1f-%.1f%%" %
          (r["mean_reduction"], r["min"], r["max"]))

    l = replanning_latency()
    print("[V-B] replanning latency: mean %.3f ms | median %.3f | max %.3f | sd %.3f" %
          (l["mean"], l["median"], l["max"], l["std"]))
    print("      = %.5f%% of the 5 s telemetry interval" % (100 * l["mean"] / 5000))

    sc = scalability()
    print("\n[V-D] scalability")
    print("  %-7s %-6s %-7s %12s %12s" % ("zones", "bpz", "bins", "cycle ms", "memory kB"))
    for row in sc:
        print("  %-7d %-6d %-7d %12.3f %12.1f" %
              (row["zones"], row["bins_per_zone"], row["total_bins"],
               row["cycle_time_ms"], row["memory_kb"]))
    x = np.array([r_["total_bins"] for r_ in sc], float)
    t = np.array([r_["cycle_time_ms"] for r_ in sc])
    m = np.array([r_["memory_kb"] for r_ in sc])

    ratios = []
    for z in (3, 4, 5):
        g = sorted([r_ for r_ in sc if r_["zones"] == z], key=lambda d: d["bins_per_zone"])
        ratios.append(g[-1]["cycle_time_ms"] / g[0]["cycle_time_ms"])
    print("  bins/zone 10->20 cycle-time ratio: %.2f-%.2fx (linear would be 2.00x)" %
          (min(ratios), max(ratios)))
    print("  max cycle time: %.3f ms at %d bins (%.4f%% of 5 s)" %
          (t.max(), int(x[t.argmax()]), 100 * t.max() / 5000))

    def r2(y, d):
        f = np.polyfit(x, y, d); res = y - np.polyval(f, x)
        return 1 - res.dot(res) / ((y - y.mean()) ** 2).sum()
    fit = np.polyfit(x, m, 1)
    print("  memory: %.1f-%.1f kB, slope %.0f B/bin, intercept %.2f kB, linear R^2 %.4f" %
          (m.min(), m.max(), fit[0] * 1024, fit[1], r2(m, 1)))

    json.dump({"route": r, "replan": l, "scale": sc,
               "mem_slope_B": float(fit[0] * 1024), "mem_intercept_kb": float(fit[1]),
               "mem_r2": float(r2(m, 1)), "cycle_ratios": ratios,
               "machine": platform.processor()},
              open("exp_e_rerun.json", "w"), indent=1)
    print("\nwritten exp_e_rerun.json")
