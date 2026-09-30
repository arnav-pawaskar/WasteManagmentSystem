# Paper experiments and figure generation

Everything reported in Section 5 of the paper is produced here. The Colab notebook
`../Distributed_Waste_Management_System.ipynb` runs the same experiments and prints
every number; these scripts additionally render the figures.

## Running

From the repository root:

```bash
python -m pip install numpy pandas matplotlib
cd experiments
python exp_e_rerun.py      # route efficiency, replanning latency, scalability
python exp_a_routing.py    # NN vs 2-opt / Or-opt / GA / exact Held-Karp  (Table 2)
python exp_a2_scaling.py   # optimizer cost vs zone size
python exp_b_gossip.py     # spillover under load, tau, message loss, node failure
python exp_c_ledger.py     # ledger latency, throughput, storage, audit  (Table 3)
python exp_d_sensor.py     # sensor-noise sensitivity + CPU-time/energy accounting
python make_figures.py     # renders ../figures/*.pdf and *.png from the JSON above
```

Each `exp_*.py` writes an `exp_*.json` alongside itself; `make_figures.py` consumes
those and writes vector PDF plus 400-dpi PNG into `../figures/`.

## Determinism

Distances, optimality gaps, storage sizes, sensor error rates and load-balancing
outcomes are fully seeded and reproduce exactly on any machine. Wall-clock timings
are hardware-dependent and vary by a few percent between runs; the values quoted in
the paper come from a single run on an AMD Ryzen 9 8945H (4.0 GHz) under CPython
3.13.15 / Windows 11, which is stated in Table 1 of the paper.

`exp_c_ledger.py` and the energy accounting in `exp_d_sensor.py` benchmark the real
`contracts/ledger.py` from this repository, not a re-implementation.
