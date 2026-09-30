"""Experiment D: sensitivity to sensor inaccuracy, plus CPU-time/energy accounting.

D1: Gaussian measurement noise and stuck-at sensor faults corrupt the reported fill
    level. Routing decisions are taken on the REPORTED value; correctness is scored
    against the GROUND-TRUTH value. Also evaluates an EWMA smoothing mitigation.
D2: CPU time per operation, and the energy that implies at the platform's rated TDP.
"""
import sys, random, time, json
import numpy as np

sys.path.insert(0, r"C:\projects\WasteManagmentSystem")
from core import BinSimulator, RouteOptimizer, BinTelemetry
from exp_a_routing import opt_nn, _tour_len, START

THRESH = 80.0


def corrupt(true_fill, rng, sigma, stuck_p, prev_reading=None):
    """Reported reading: Gaussian noise, plus a stuck-at fault that repeats the
    previous reading (the classic failure mode of a fouled ultrasonic sensor)."""
    if stuck_p > 0 and rng.random() < stuck_p and prev_reading is not None:
        return prev_reading, True
    r = true_fill + rng.gauss(0, sigma)
    return max(0.0, min(100.0, r)), False


def run_sensor_experiment(sigma, stuck_p, filt="raw", alpha=0.5,
                          n_runs=20, zones=3, bpz=15, steps=9):
    """filt: 'raw' | 'ewma' (alpha) | 'median3' (median of the last 3 readings)."""
    opt = RouteOptimizer()
    fp = fn = tp = actual_pos = 0
    dist_sensor, dist_oracle = 0.0, 0.0
    for run in range(n_runs):
        sim = BinSimulator(zones, bpz, seed=1000 + run)
        rng = random.Random(80000 + run * 31 + int(sigma * 10) + int(stuck_p * 100))
        readings = {b.bin_id: None for b in sim.bins}
        smoothed = {b.bin_id: None for b in sim.bins}
        history = {b.bin_id: [] for b in sim.bins}
        for t in range(steps):
            sim.step(t)
            for b in sim.bins:
                r, _ = corrupt(b.fill_level, rng, sigma, stuck_p, readings[b.bin_id])
                readings[b.bin_id] = r
                history[b.bin_id].append(r)
                if smoothed[b.bin_id] is None:
                    smoothed[b.bin_id] = r
                else:
                    smoothed[b.bin_id] = alpha * r + (1 - alpha) * smoothed[b.bin_id]
        if filt == "ewma":
            obs = smoothed
        elif filt == "median3":
            obs = {k: float(np.median(v[-3:])) for k, v in history.items()}
        else:
            obs = readings
        for z in range(1, zones + 1):
            zb = sim.bins_by_zone(z)
            true_over = [b for b in zb if b.fill_level >= THRESH]
            sens_over = [b for b in zb if obs[b.bin_id] >= THRESH]
            true_ids = {b.bin_id for b in true_over}
            sens_ids = {b.bin_id for b in sens_over}
            actual_pos += len(true_ids)
            tp += len(true_ids & sens_ids)
            fp += len(sens_ids - true_ids)
            fn += len(true_ids - sens_ids)
            # distance actually driven (sensor-selected set) vs the oracle set
            if sens_over:
                pts = [(b.x, b.y) for b in sens_over]
                dist_sensor += _tour_len(opt_nn(pts, START), pts, START)
            if true_over:
                pts = [(b.x, b.y) for b in true_over]
                dist_oracle += _tour_len(opt_nn(pts, START), pts, START)
    # Efficiency metric: distance actually driven per TRUE overflow serviced.
    # (Raw distance is not comparable: missing bins shortens the route.)
    eff_sensor = dist_sensor / max(1, tp)
    eff_oracle = dist_oracle / max(1, actual_pos)
    return {
        "sigma": sigma, "stuck_p": stuck_p, "filter": filt,
        "actual_positives": actual_pos, "tp": tp, "fp": fp, "fn": fn,
        "fp_rate_pct": 100.0 * fp / max(1, actual_pos),
        "miss_rate_pct": 100.0 * fn / max(1, actual_pos),
        "dist_per_serviced": eff_sensor, "dist_per_serviced_oracle": eff_oracle,
        "eff_penalty_pct": 100.0 * (eff_sensor - eff_oracle) / eff_oracle,
    }


def d1():
    print("=" * 100)
    print("D1a  GAUSSIAN SENSOR NOISE  (3 zones x 15 bins, 20 runs, threshold 80%)")
    print("=" * 100)
    print("%-10s %12s %12s %14s %14s" %
          ("sigma (pp)", "missed %", "false-pos %", "km/bin pen %", "true overflows"))
    rows = []
    for s in [0.0, 1.0, 2.0, 5.0, 10.0]:
        r = run_sensor_experiment(s, 0.0)
        rows.append(r)
        print("%-10.1f %12.2f %12.2f %14.2f %14d" %
              (s, r["miss_rate_pct"], r["fp_rate_pct"], r["eff_penalty_pct"],
               r["actual_positives"]))

    print()
    print("=" * 100)
    print("D1b  STUCK-AT SENSOR FAULTS  (sigma fixed at 2.0 pp; p = chance a reading repeats)")
    print("=" * 100)
    print("%-10s %12s %12s %14s" % ("stuck p", "missed %", "false-pos %", "km/bin pen %"))
    for p in [0.0, 0.05, 0.10, 0.20, 0.40]:
        r = run_sensor_experiment(2.0, p)
        rows.append(r)
        print("%-10.2f %12.2f %12.2f %14.2f" %
              (p, r["miss_rate_pct"], r["fp_rate_pct"], r["eff_penalty_pct"]))

    print()
    print("=" * 100)
    print("D1c  FILTERING AS MITIGATION  (sigma swept, stuck_p = 0.10)")
    print("=" * 100)
    print("%-8s %10s %10s %10s | %10s %10s %10s" %
          ("sigma", "raw miss", "ewma miss", "med3 miss", "raw fp", "ewma fp", "med3 fp"))
    for s in [1.0, 2.0, 5.0, 10.0]:
        a = run_sensor_experiment(s, 0.10, filt="raw")
        b = run_sensor_experiment(s, 0.10, filt="ewma")
        c = run_sensor_experiment(s, 0.10, filt="median3")
        rows += [b, c]
        print("%-8.1f %10.2f %10.2f %10.2f | %10.2f %10.2f %10.2f" %
              (s, a["miss_rate_pct"], b["miss_rate_pct"], c["miss_rate_pct"],
               a["fp_rate_pct"], b["fp_rate_pct"], c["fp_rate_pct"]))
    return rows


def d2():
    """CPU time per operation and the energy it implies at the rated package TDP."""
    from contracts.ledger import PermissionedLedger, ValidatorRegistry, EventType
    print()
    print("=" * 100)
    print("D2  CPU TIME PER OPERATION  (process_time; single-threaded)")
    print("=" * 100)
    PAYLOAD = {"bin_id": "bin_1_7", "fill_level": 93.4, "truck_id": "truck_1",
               "lat": 19.1071, "lon": 72.8370, "serviced_at": "2026-03-01T09:14:22"}
    reg = ValidatorRegistry()
    for i in range(4):
        reg.register(f"fog_{i+1}")
    L = PermissionedLedger(reg, block_size=8)
    # Windows process_time ticks at ~15.625 ms, so N is sized to make total CPU
    # time several seconds and the quantisation error <0.5%.
    N = 400000
    t0 = time.process_time()
    for i in range(N):
        L.submit(EventType.BIN_SERVICED, 1, PAYLOAD, "fog_1")
    tot_tx = time.process_time() - t0
    cpu_tx = tot_tx / N * 1000

    # routing cycle: 3 zones, default config
    opt = RouteOptimizer()
    sim = BinSimulator(3, 15, seed=4315)
    for t in range(24):
        sim.step(t)
    zb = [sim.bins_by_zone(z) for z in range(1, 4)]
    M = 60000
    t0 = time.process_time()
    for _ in range(M):
        for z, b in enumerate(zb, start=1):
            opt.nearest_neighbour_route(b, zone_id=z)
    tot_cy = time.process_time() - t0
    cpu_cycle = tot_cy / M * 1000

    TDP_W = 45.0   # Intel Core i9-9880H rated package TDP
    print("  total CPU: ledger %.3f s over %d tx | routing %.3f s over %d cycles" % (tot_tx, N, tot_cy, M))
    print("  ledger transaction  : %.5f ms CPU  ->  %.2f uJ at %.0f W (upper bound)" %
          (cpu_tx, cpu_tx * 1e-3 * TDP_W * 1e6, TDP_W))
    print("  full routing cycle  : %.5f ms CPU  ->  %.2f uJ at %.0f W (upper bound)" %
          (cpu_cycle, cpu_cycle * 1e-3 * TDP_W * 1e6, TDP_W))
    # per-bin daily energy for a 10 000-bin city: 1 tx + share of routing cycle
    print()
    print("  10 000-bin city, 1 collection/bin/day, 1 routing cycle per 5 s per zone:")
    tx_day = 10000
    cycles_day = 86400 / 5
    e_tx = tx_day * cpu_tx * 1e-3 * TDP_W          # joules
    e_rt = cycles_day * cpu_cycle * 1e-3 * TDP_W
    print("    ledger  : %.2f J/day  (%.4f Wh/day)" % (e_tx, e_tx / 3600))
    print("    routing : %.2f J/day  (%.4f Wh/day)" % (e_rt, e_rt / 3600))
    return {"cpu_ms_per_tx": cpu_tx, "cpu_ms_per_cycle": cpu_cycle, "tdp_w": TDP_W,
            "uj_per_tx": cpu_tx * 1e-3 * TDP_W * 1e6,
            "uj_per_cycle": cpu_cycle * 1e-3 * TDP_W * 1e6,
            "ledger_J_day": e_tx, "routing_J_day": e_rt}


if __name__ == "__main__":
    rows = d1()
    e = d2()
    json.dump({"sensor": rows, "energy": e}, open("exp_d_sensor.json", "w"), indent=1)
    print("\nwritten exp_d_sensor.json")
