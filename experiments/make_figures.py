"""Generate every figure in the paper as vector PDF (and 400-dpi PNG)."""
import json, os, math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

OUT = r"C:\projects\WasteManagmentSystem\figures"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 120, "savefig.dpi": 400,
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9.5,
    "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "pdf.fonttype": 42, "ps.fonttype": 42,
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "serif"],
})

GREY = ["#222222", "#555555", "#888888", "#AAAAAA", "#CCCCCC"]
HATCH = ["", "///", "\\\\\\", "xxx", "..."]


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".pdf"))
    fig.savefig(os.path.join(OUT, name + ".png"))
    plt.close(fig)
    print("  wrote", name + ".pdf/.png")


D = {k: json.load(open(f"exp_{k}.json"))
     for k in ["a_routing", "a2_scaling", "b_gossip", "c_ledger", "d_sensor", "e_rerun"]}


# ---------------------------------------------------------------- Fig. 1
def fig_architecture():
    fig, ax = plt.subplots(figsize=(7.2, 4.1))
    ax.set_xlim(0, 100); ax.set_ylim(0, 78); ax.axis("off")

    def arrow(p, q, ls="-", lw=1.5, style="-|>", ms=11):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=ms,
                                     lw=lw, ls=ls, color="black",
                                     shrinkA=1, shrinkB=1, zorder=5))

    def panel(x, y, w, h, title, lines, fc="white", lw=1.2, ls="-",
              tsz=8.8, ssz=7.0):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5",
                                    fc=fc, ec="black", lw=lw, linestyle=ls, zorder=2))
        ax.text(x + w / 2, y + h - 2.6, title, ha="center", va="top",
                fontsize=tsz, fontweight="bold", zorder=3)
        if lines:
            ax.text(x + w / 2, y + h - 7.4, lines, ha="center", va="top",
                    fontsize=ssz, linespacing=1.5, zorder=3)

    # asynchronous tiers, drawn dashed and kept off the decision path
    panel(16, 66, 26, 10, "Cloud Layer", "history - analytics", ls="--", ssz=6.9)
    panel(58, 66, 26, 10, "Application Layer", "operator dashboard", ls="--", ssz=6.9)

    # fog layer: a container holding two peer fog nodes
    ax.add_patch(FancyBboxPatch((27, 26), 46, 32, boxstyle="round,pad=0.5",
                                fc="#ECECEC", ec="black", lw=1.4, zorder=1))
    ax.text(50, 56.8, "Fog Layer", ha="center", va="top",
            fontsize=9, fontweight="bold", zorder=3)
    for x0, zl in ((29.0, "$i$"), (52.5, "$j$")):
        ax.add_patch(FancyBboxPatch((x0, 30), 18.5, 20, boxstyle="round,pad=0.4",
                                    fc="white", ec="black", lw=1.0, zorder=2))
        ax.text(x0 + 9.25, 48.6, "Fog node, Zone " + zl, ha="center", va="top",
                fontsize=7.3, fontweight="bold", zorder=3)
        ax.text(x0 + 9.25, 44.6,
                "priority + NN routing\nspillover + election\nledger client",
                ha="center", va="top", fontsize=6.3, linespacing=1.6, zorder=3)
    arrow((47.8, 35.0), (52.2, 35.0), style="<|-|>", lw=1.4, ms=9)
    ax.text(50, 32.4, "gossip + spillover", ha="center", va="center",
            fontsize=6.2, style="italic", zorder=6,
            bbox=dict(fc="white", ec="none", pad=0.5))

    # IoT and collection tiers
    panel(1, 32, 23, 20, "IoT Layer",
          "Smart bins\nultrasonic fill\n+ location, every 5 s", fc="#F7F7F7", ssz=6.9)
    panel(76, 32, 23, 20, "Collection Layer",
          "Garbage trucks\nRoutePlan dispatch\nand replanning",
          fc="#F7F7F7", ssz=6.9)

    # solid arrows: the real-time critical path, bins -> fog -> trucks
    arrow((24.6, 42), (26.4, 42))
    arrow((73.6, 42), (75.4, 42))

    # dashed arrows: asynchronous upload, off the decision path
    arrow((37, 58.6), (31, 65.4), ls="--", lw=1.0)
    arrow((63, 58.6), (69, 65.4), ls="--", lw=1.0)

    # ledger band spans the fog and collection tiers only
    ax.add_patch(Rectangle((27, 15), 72, 7, fc="#D5D5D5", ec="black",
                           lw=1.1, zorder=0))
    ax.text(63, 18.5, "Permissioned append-only ledger:   bin serviced  |  route "
                      "completed  |  spillover  |  zone snapshot",
            ha="center", va="center", fontsize=6.8, zorder=3)
    arrow((50, 25.4), (50, 22.4), lw=1.0, ms=9)
    arrow((87.5, 31.4), (87.5, 22.4), lw=1.0, ms=9)

    ax.plot([3, 11], [8.0, 8.0], color="black", lw=1.5)
    ax.text(12.5, 8.0, "real-time critical path (no cloud round trip)",
            va="center", fontsize=7.0)
    ax.plot([3, 11], [3.5, 3.5], color="black", lw=1.0, ls="--")
    ax.text(12.5, 3.5, "asynchronous flow, off the decision path",
            va="center", fontsize=7.0)
    save(fig, "fig_architecture")


# ---------------------------------------------------------------- Fig. 2
def fig_literature():
    papers = [("Ariton 2008", 0, 0, 0, 0, 0), ("Garach 2017", 0, 1, 0, 0, 0),
              ("Singhvi 2019", 1, 0, 0, 0, 0), ("Damadi 2021", 1, 1, 0, 1, 0),
              ("Ahmad 2021", 1, 0, 0, 1, 0), ("Ghahramani 2022", 1, 0, 1, 0, 0),
              ("Khanh 2023", 0, 1, 0, 0, 1), ("Nwokediegwu 2024", 1, 0, 1, 0, 0),
              ("Choubey 2024", 1, 1, 0, 0, 0), ("Palagan 2025", 1, 1, 0, 1, 0),
              ("Alourani 2025", 1, 0, 0, 0, 0), ("Anitha 2025", 1, 0, 1, 0, 0),
              ("This work", 1, 1, 1, 1, 1)]
    labels = ["IoT\nsensing", "Fog\ncomputing", "Route\noptimization",
              "Blockchain\nledger", "P2P load\nbalancing"]
    M = np.array([p[1:] for p in papers], float)
    names = [p[0] for p in papers]

    fig, ax = plt.subplots(figsize=(5.0, 4.2))
    ax.imshow(M, cmap="Greys", vmin=0, vmax=1.45, aspect="auto")
    ax.set_xticks(range(5)); ax.set_xticklabels(labels, fontsize=7.4)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=7.6)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, "Y" if M[i, j] else "-", ha="center", va="center",
                    fontsize=7.4, color="white" if M[i, j] else "#333333",
                    fontweight="bold" if M[i, j] else "normal")
    for s in ax.spines.values():
        s.set_visible(True)
    ax.set_xticks(np.arange(-.5, 5, 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(names), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", length=0)
    ax.get_yticklabels()[-1].set_fontweight("bold")
    ax.set_title("Capability coverage of the comparison set", fontsize=9)
    save(fig, "fig_lit_feature_matrix")


# ---------------------------------------------------------------- Fig. 3
def fig_routing():
    rows = D["a_routing"]["rows"]
    names = ["Sequential (fixed order)", "Nearest Neighbour", "NN + 2-opt",
             "NN + 2-opt + Or-opt", "Genetic algorithm", "Exact (Held-Karp)"]
    short = ["Sequential", "NN", "NN+2-opt", "NN+2opt\n+Or-opt", "GA", "Exact"]
    gaps, times = [], []
    for nm in names:
        g = [100 * (r[nm] - r["Exact (Held-Karp)"]) / r["Exact (Held-Karp)"] for r in rows]
        gaps.append(np.mean(g))
        times.append(np.mean([r[nm + "__ms"] for r in rows]))

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    x = np.arange(len(short))
    b = axes[0].bar(x, gaps, color=GREY[2], edgecolor="black", lw=0.8)
    for xi, g in zip(x, gaps):
        axes[0].text(xi, g + 1.1, f"{g:.2f}", ha="center", fontsize=7)
    axes[0].set_xticks(x); axes[0].set_xticklabels(short, fontsize=7.2)
    axes[0].set_ylabel("Mean excess over optimal (%)")
    axes[0].set_title("(a) Route quality vs exact optimum", fontsize=9)
    axes[0].set_ylim(0, max(gaps) * 1.22)

    sc = D["a2_scaling"]
    algos = ["Nearest Neighbour", "NN + 2-opt", "NN + 2-opt + Or-opt",
             "Genetic algorithm", "Exact (Held-Karp)"]
    mk = ["o", "s", "^", "D", "v"]
    for a, m, c in zip(algos, mk, GREY[:1] + GREY[1:]):
        pts = sorted([(r["n"], r["ms_median"]) for r in sc if r["algo"] == a])
        axes[1].plot([p[0] for p in pts], [p[1] for p in pts], marker=m, ms=3.6,
                     lw=1.2, color=c, label=a.replace("Nearest Neighbour", "NN"))
    axes[1].axhline(5000, color="black", ls=":", lw=1.1)
    axes[1].text(6, 6200, "5 s telemetry interval", fontsize=6.8)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("Overflowing bins in the zone")
    axes[1].set_ylabel("Compute time (ms, log)")
    axes[1].set_title("(b) Cost scaling", fontsize=9)
    axes[1].legend(fontsize=6.4, loc="lower right", frameon=False)
    save(fig, "fig_routing_comparison")


# ---------------------------------------------------------------- Fig. 4
def fig_spillover():
    b = D["b_gossip"]
    fig, axes = plt.subplots(1, 4, figsize=(7.4, 2.35))

    ld = b["load"]
    hm = [r["hot_mult"] for r in ld]
    axes[0].plot(hm, [r["without"]["max_load"] for r in ld], "o-", ms=3.4, lw=1.2,
                 color=GREY[0], label="without")
    axes[0].plot(hm, [r["with"]["max_load"] for r in ld], "s--", ms=3.4, lw=1.2,
                 color=GREY[2], label="with")
    axes[0].set_xlabel("Hot-zone fill multiplier")
    axes[0].set_ylabel("Peak zone backlog (bins)")
    axes[0].set_title("(a) Load", fontsize=8.5)
    axes[0].legend(fontsize=6.6, frameon=False)

    tu = b["tau"]
    t = [r["tau"] for r in tu]
    w = 0.36; xt = np.arange(len(t))
    axes[1].bar(xt - w / 2, [r["std_no"] for r in tu], w, color=GREY[0],
                edgecolor="black", lw=0.6, label="without")
    axes[1].bar(xt + w / 2, [r["std_sp"] for r in tu], w, color=GREY[3],
                edgecolor="black", lw=0.6, label="with")
    axes[1].set_xticks(xt); axes[1].set_xticklabels(t)
    axes[1].set_xlabel(r"Overload threshold $\tau$")
    axes[1].set_ylabel("Load imbalance (s.d.)")
    axes[1].set_title(r"(b) Threshold", fontsize=8.5)
    axes[1].legend(fontsize=6.6, frameon=False)

    ls = b["loss"]
    lo = [100 * r["loss"] for r in ls]
    axes[2].plot(lo, [r["transfers"] for r in ls], "o-", ms=3.4, lw=1.2,
                 color=GREY[0], label="transfers")
    axes[2].plot(lo, [r["view_err"] for r in ls], "^--", ms=3.4, lw=1.2,
                 color=GREY[2], label="view error")
    axes[2].set_xlabel("Message loss (%)")
    axes[2].set_ylabel("Transfers / view error (bins)")
    axes[2].set_title("(c) Loss", fontsize=8.5)
    axes[2].legend(fontsize=6.6, frameon=False)

    fl = b["failure"]
    fx = [r["failed"] for r in fl]
    axes[3].plot(fx, [r["max"] for r in fl], "o-", ms=3.4, lw=1.2, color=GREY[0],
                 label="peak backlog")
    ax2 = axes[3].twinx()
    ax2.plot(fx, [r["transfers"] for r in fl], "s--", ms=3.4, lw=1.2,
             color=GREY[2], label="transfers")
    ax2.set_ylabel("Transfers", fontsize=8)
    ax2.spines["top"].set_visible(False)
    axes[3].set_xlabel("Failed fog nodes (of 5)")
    axes[3].set_ylabel("Peak backlog (bins)")
    axes[3].set_title("(d) Node failure", fontsize=8.5)
    axes[3].set_xticks(fx)
    h1, l1 = axes[3].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    axes[3].legend(h1 + h2, l1 + l2, fontsize=6.2, frameon=False, loc="lower left")
    fig.tight_layout()
    save(fig, "fig_spillover")


# ---------------------------------------------------------------- Fig. 5
def fig_ledger():
    c = D["c_ledger"]
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.35))

    v = c["c2"]
    axes[0].plot([r["validators"] for r in v], [r["mean_ms"] for r in v],
                 "o-", ms=3.6, lw=1.3, color=GREY[0])
    axes[0].set_xlabel("Validators in the set")
    axes[0].set_ylabel("Block seal latency (ms)")
    axes[0].set_title("(a) Validator-set size", fontsize=8.5)
    axes[0].set_xticks([r["validators"] for r in v])

    bs = c["c3"]
    axes[1].plot([r["block_size"] for r in bs], [r["ms_per_tx"] for r in bs],
                 "s-", ms=3.6, lw=1.3, color=GREY[0])
    axes[1].set_xscale("log", base=2)
    axes[1].set_xlabel("Transactions per block")
    axes[1].set_ylabel("Amortised cost (ms/tx)")
    axes[1].set_title("(b) Batching", fontsize=8.5)

    st = c["c4"]; vf = c["c5"]
    axes[2].plot([r["tx"] for r in st], [r["bytes"] / 1e6 for r in st],
                 "o-", ms=3.6, lw=1.3, color=GREY[0], label="storage (MB)")
    ax2 = axes[2].twinx()
    ax2.plot([r["tx"] for r in vf], [r["verify_ms"] for r in vf],
             "^--", ms=3.6, lw=1.3, color=GREY[2], label="audit (ms)")
    ax2.set_ylabel("Full-chain audit (ms)", fontsize=8)
    ax2.spines["top"].set_visible(False)
    axes[2].set_xlabel("Committed transactions")
    axes[2].set_ylabel("Chain size (MB)")
    axes[2].set_title("(c) Growth", fontsize=8.5)
    h1, l1 = axes[2].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    axes[2].legend(h1 + h2, l1 + l2, fontsize=6.4, frameon=False, loc="upper left")
    fig.tight_layout()
    save(fig, "fig_ledger")


# ---------------------------------------------------------------- Fig. 6
def fig_scale_sensor():
    e = D["e_rerun"]["scale"]
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.35))

    for z, mk in zip((3, 4, 5), ("o", "s", "^")):
        g = sorted([r for r in e if r["zones"] == z], key=lambda d: d["bins_per_zone"])
        axes[0].plot([r["bins_per_zone"] for r in g], [r["cycle_time_ms"] for r in g],
                     marker=mk, ms=3.6, lw=1.2,
                     color=GREY[{3: 0, 4: 1, 5: 2}[z]], label=f"{z} zones")
    axes[0].set_xlabel("Bins per zone"); axes[0].set_ylabel("Routing cycle (ms)")
    axes[0].set_title("(a) Compute", fontsize=8.5)
    axes[0].legend(fontsize=6.8, frameon=False)

    x = np.array([r["total_bins"] for r in e], float)
    m = np.array([r["memory_kb"] for r in e])
    o = np.argsort(x)
    axes[1].plot(x[o], m[o], "o", ms=4, color=GREY[0])
    fit = np.polyfit(x, m, 1)
    xs = np.linspace(x.min(), x.max(), 50)
    axes[1].plot(xs, np.polyval(fit, xs), "--", lw=1.1, color=GREY[2],
                 label=r"$R^2=%.4f$" % D["e_rerun"]["mem_r2"])
    axes[1].set_xlabel("Total bins"); axes[1].set_ylabel("Memory (kB)")
    axes[1].set_title("(b) Memory", fontsize=8.5)
    axes[1].legend(fontsize=6.8, frameon=False)

    s = [r for r in D["d_sensor"]["sensor"] if r["stuck_p"] == 0.0 and r["filter"] == "raw"]
    s = sorted(s, key=lambda r: r["sigma"])
    sg = [r["sigma"] for r in s]
    axes[2].plot(sg, [r["miss_rate_pct"] for r in s], "o-", ms=3.6, lw=1.2,
                 color=GREY[0], label="missed overflows")
    axes[2].plot(sg, [r["fp_rate_pct"] for r in s], "s--", ms=3.6, lw=1.2,
                 color=GREY[2], label="false alarms")
    axes[2].plot(sg, [r["eff_penalty_pct"] for r in s], "^:", ms=3.6, lw=1.2,
                 color=GREY[1], label="distance/bin penalty")
    axes[2].set_xlabel(r"Sensor noise $\sigma$ (percentage points)")
    axes[2].set_ylabel("Rate (%)")
    axes[2].set_title("(c) Sensor error", fontsize=8.5)
    axes[2].legend(fontsize=6.4, frameon=False)
    fig.tight_layout()
    save(fig, "fig_scalability")


if __name__ == "__main__":
    print("writing figures to", OUT)
    fig_architecture()
    fig_literature()
    fig_routing()
    fig_spillover()
    fig_ledger()
    fig_scale_sensor()
    print("done")
