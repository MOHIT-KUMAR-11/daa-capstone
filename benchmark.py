"""
Phase 4 - Performance testing.

Measures the runtime of every major step on growing inputs, checks TSP
solution quality against the exact optimum, and draws the charts used in
the report. Results go to results/*.csv and results/*.png.

    python benchmark.py            # full run (~1 minute)
    python benchmark.py --quick    # smaller sizes, for a fast check
"""

import argparse
import csv
import gc
import os
import random
import statistics
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from courier.generator import generate_city, generate_parcels  # noqa: E402
from courier.graph import Graph, dijkstra  # noqa: E402
from courier.io_utils import load_parcels  # noqa: E402
from courier.knapsack import knapsack_01  # noqa: E402
from courier.planner import STEP_NAMES, PlanConfig, plan_deliveries  # noqa: E402
from courier.sorting import SORTING_ALGORITHMS, parcel_priority_key  # noqa: E402
from courier.tsp import (build_distance_matrix, held_karp,  # noqa: E402
                         nearest_neighbor_tour, tour_length, two_opt)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")

# Validated categorical palette, used in fixed slot order.
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
TEXT, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
    "ytick.color": MUTED, "text.color": TEXT, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 6,
})


def timeit(fn, repeats=5):
    """Best (minimum) wall-clock seconds of `repeats` runs. The minimum is
    the least affected by other processes running on the machine."""
    times = []
    gc.collect()
    gc.disable()          # like the standard `timeit` module: no GC pauses inside a run
    try:
        for _ in range(repeats):
            t0 = time.perf_counter()
            fn()
            times.append(time.perf_counter() - t0)
    finally:
        gc.enable()
    return min(times)


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=150)
    plt.close(fig)
    print(f"  -> results/{name}")


# --------------------------------------------------------------------------
def bench_sorting(sizes):
    print("Sorting ...")
    rows = []
    for n in sizes:
        parcels = generate_parcels(n, 50, seed=n)
        row = [n]
        for name, fn in SORTING_ALGORITHMS.items():
            if name == "insertion_sort" and n > 5000:
                row.append("")
                continue
            row.append(timeit(lambda: fn(parcels, key=parcel_priority_key)) * 1000)
        row.append(timeit(lambda: sorted(parcels, key=parcel_priority_key)) * 1000)
        rows.append(row)
        print("  n=%-6d " % n + "  ".join(f"{x:9.2f}" if x != "" else "    skip " for x in row[1:]))
    header = ["n"] + list(SORTING_ALGORITHMS) + ["python_sorted"]
    write_csv("bench_sorting.csv", header, rows)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    for i, name in enumerate(header[1:]):
        pts = [(r[0], r[i + 1]) for r in rows if r[i + 1] != ""]
        ax.plot(*zip(*pts), marker="o", color=C[i], label=name.replace("_", " "))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("number of parcels n (log)")
    ax.set_ylabel("time, ms (log)")
    ax.set_title("Sorting parcels: O(n²) insertion vs O(n log n) sorts")
    ax.legend(loc="upper left")
    save(fig, "chart_sorting.png")


def bench_knapsack(ns, caps):
    print("Knapsack ...")
    rows_n, rows_w = [], []
    for n in ns:
        items = generate_parcels(n, 50, seed=n)
        t = timeit(lambda: knapsack_01(items, 100)) * 1000
        rows_n.append([n, 100, t, n * 101])
        print(f"  n={n:<5} W=100   {t:9.2f} ms")
    for W in caps:
        items = generate_parcels(200, 50, seed=W)
        t = timeit(lambda: knapsack_01(items, W)) * 1000
        rows_w.append([200, W, t, 200 * (W + 1)])
        print(f"  n=200   W={W:<5} {t:9.2f} ms")
    write_csv("bench_knapsack.csv", ["n", "capacity_W", "ms", "dp_cells"], rows_n + rows_w)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([r[3] for r in rows_n], [r[2] for r in rows_n], marker="o", color=C[0],
            label="vary n (W = 100)")
    ax.plot([r[3] for r in rows_w], [r[2] for r in rows_w], marker="s", color=C[1],
            label="vary W (n = 200)")
    ax.set_xlabel("DP table cells  n × (W+1)")
    ax.set_ylabel("time, ms")
    ax.set_title("0/1 knapsack DP grows linearly with n·W")
    ax.legend(loc="upper left")
    save(fig, "chart_knapsack.png")


def bench_dijkstra(sizes):
    print("Dijkstra ...")
    rows = []
    for v in sizes:
        g = Graph.from_edges(generate_city(v, seed=v))
        t = timeit(lambda: dijkstra(g, "D")) * 1000
        rows.append([len(g.nodes), g.edge_count(), t])
        print(f"  V={len(g.nodes):<5} E={g.edge_count():<5} {t:9.2f} ms")
    write_csv("bench_dijkstra.csv", ["V", "E", "ms"], rows)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([r[0] for r in rows], [r[2] for r in rows], marker="o", color=C[0])
    ax.set_xlabel("graph nodes V  (E ≈ 2–3·V)")
    ax.set_ylabel("time, ms")
    ax.set_title("Dijkstra with binary heap: O((V+E) log V)")
    save(fig, "chart_dijkstra.png")


def bench_tsp(stop_counts, hk_max, instances):
    print("TSP quality and runtime ...")
    g = Graph.from_edges(generate_city(300, seed=99))
    customers = [n for n in g.nodes if n != "D"]
    rng = random.Random(42)
    rows = []
    for k in stop_counts:
        nn_r, opt_r, t_nn, t_2o, t_hk = [], [], [], [], []
        for _ in range(instances):
            pts = ["D"] + rng.sample(customers, k)
            dm, _ = build_distance_matrix(g, pts)
            t0 = time.perf_counter(); nn = nearest_neighbor_tour("D", pts, dm); t_nn.append(time.perf_counter() - t0)
            t0 = time.perf_counter(); im = two_opt(nn, dm); t_2o.append(time.perf_counter() - t0)
            if k <= hk_max:
                t0 = time.perf_counter(); opt, _ = held_karp("D", pts, dm); t_hk.append(time.perf_counter() - t0)
                nn_r.append(tour_length(nn, dm) / opt)
                opt_r.append(tour_length(im, dm) / opt)
        row = [k, statistics.mean(t_nn) * 1000, statistics.mean(t_2o) * 1000,
               statistics.mean(t_hk) * 1000 if t_hk else "",
               statistics.mean(nn_r) if nn_r else "", max(nn_r) if nn_r else "",
               statistics.mean(opt_r) if opt_r else "", max(opt_r) if opt_r else ""]
        rows.append(row)
        print("  k=%-4d NN %.3f ms  2opt %.3f ms  HK %s  NN/opt %s  2opt/opt %s" % (
            k, row[1], row[2], f"{row[3]:.1f} ms" if row[3] != "" else "-",
            f"{row[4]:.3f}" if row[4] != "" else "-", f"{row[6]:.3f}" if row[6] != "" else "-"))
    write_csv("bench_tsp.csv", ["stops", "nn_ms", "two_opt_ms", "held_karp_ms",
                                "nn_ratio_mean", "nn_ratio_max", "two_opt_ratio_mean",
                                "two_opt_ratio_max"], rows)

    q = [r for r in rows if r[4] != ""]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([r[0] for r in q], [(r[4] - 1) * 100 for r in q], marker="o", color=C[0],
            label="nearest neighbour")
    ax.plot([r[0] for r in q], [(r[6] - 1) * 100 for r in q], marker="s", color=C[1],
            label="nearest neighbour + 2-opt")
    ax.axhline(0, color=MUTED, linewidth=1)
    ax.set_xlabel("stops in the trip")
    ax.set_ylabel("% longer than optimal (mean)")
    ax.set_title(f"Route quality vs exact Held-Karp ({instances} random trips per size)")
    ax.legend(loc="upper left")
    save(fig, "chart_tsp_quality.png")

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot([r[0] for r in rows], [r[1] for r in rows], marker="o", color=C[0], label="nearest neighbour O(k²)")
    ax.plot([r[0] for r in rows], [r[2] for r in rows], marker="s", color=C[1], label="2-opt")
    hk = [r for r in rows if r[3] != ""]
    ax.plot([r[0] for r in hk], [r[3] for r in hk], marker="^", color=C[2], label="Held-Karp exact O(2ᵏk²)")
    ax.set_yscale("log")
    ax.set_xlabel("stops in the trip k")
    ax.set_ylabel("time, ms (log)")
    ax.set_title("Route runtime: heuristics stay fast, exact DP explodes")
    ax.legend(loc="upper left")
    save(fig, "chart_tsp_runtime.png")


def bench_pipeline(configs):
    print("End-to-end pipeline ...")
    rows = []
    for label, name, cap, vans, window, *rest in configs:
        use_two_opt = rest[0] if len(rest) > 0 else True
        cache = rest[1] if len(rest) > 1 else True
        parcels = load_parcels(os.path.join(HERE, "data", f"{name}_parcels.csv"))
        g = Graph.from_csv(os.path.join(HERE, "data", f"{name}_edges.csv"))
        cfg = PlanConfig(capacity_kg=cap, vehicles=vans, window_factor=window,
                         use_two_opt=use_two_opt, cache_paths=cache)
        gc.collect()
        gc.disable()
        try:
            runs = [plan_deliveries(parcels, g, cfg) for _ in range(5)]
        finally:
            gc.enable()
        steps = {s: min(r.timings[s] for r in runs) * 1000 for s in STEP_NAMES}
        res = runs[0]
        rows.append([label, len(parcels), len(g.nodes), cap, vans, window, len(res.trips),
                     round(res.total_km, 1), len(res.late)] + [round(steps[s], 3) for s in STEP_NAMES])
        print(f"  {label:<26} trips={len(res.trips):<3} km={res.total_km:8.1f} late={len(res.late):<4} "
              + " ".join(f"{s}={steps[s]:.2f}" for s in STEP_NAMES))
    header = ["config", "parcels", "nodes", "capacity", "vans", "window", "trips", "total_km",
              "late"] + [f"{s}_ms" for s in STEP_NAMES]
    write_csv("bench_pipeline.csv", header, rows)

    # stacked share of runtime per step for the three base datasets
    base = rows[:3]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    labels = [f"{r[0]}\n({r[1]} parcels)" for r in base]
    left = [0.0] * len(base)
    for i, s in enumerate(STEP_NAMES):
        vals = [r[9 + i] for r in base]
        tot = [sum(r[9:]) for r in base]
        share = [100 * v / t for v, t in zip(vals, tot)]
        ax.barh(labels, share, left=left, color=C[i], label=s.replace("_", " "),
                edgecolor=SURFACE, linewidth=2, height=0.55)
        left = [a + b for a, b in zip(left, share)]
    ax.set_xlabel("share of planner runtime (%)")
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_title("Where the planner spends its time")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=5)
    for r, y in zip(base, range(len(base))):
        ax.text(101, y, f"{sum(r[9:]):.1f} ms", va="center", color=MUTED, fontsize=9)
    save(fig, "chart_pipeline_steps.png")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.quick:
        bench_sorting([100, 500, 1000])
        bench_knapsack([50, 100, 200], [50, 100, 200])
        bench_dijkstra([100, 500, 1000])
        bench_tsp([4, 6, 8, 20], hk_max=8, instances=5)
    else:
        bench_sorting([100, 500, 1000, 2000, 5000, 10000, 20000])
        bench_knapsack([50, 100, 200, 400, 800, 1600], [50, 100, 200, 400, 800])
        bench_dijkstra([100, 250, 500, 1000, 2000, 3000])
        bench_tsp([3, 4, 5, 6, 7, 8, 9, 10, 11, 20, 40, 80], hk_max=11, instances=20)
    bench_pipeline([
        ("small", "small", 40, 1, 0),
        ("medium", "medium", 60, 1, 0),
        ("large", "large", 120, 1, 0),
        ("large, no path cache", "large", 120, 1, 0, True, False),
        ("medium, 3 vans", "medium", 60, 3, 0),
        ("medium, 3 vans, window 1.5", "medium", 60, 3, 1.5),
        ("large, 10 vans", "large", 120, 10, 0),
        ("large, 10 vans, window 1.5", "large", 120, 10, 1.5),
        ("large, 10 vans, no 2-opt", "large", 120, 10, 0, False),
    ])


if __name__ == "__main__":
    main()
