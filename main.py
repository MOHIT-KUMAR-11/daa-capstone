"""
Mini-Courier Planner - command-line entry point.

Examples
    python main.py                                   # small dataset, full trace
    python main.py --dataset medium --capacity 60
    python main.py --parcels my_parcels.csv --edges my_edges.csv --capacity 40
    python main.py --dataset small --save results/trace_small.txt
"""

import argparse
import io
import os
import sys
from contextlib import redirect_stdout

from courier.graph import Graph, dijkstra, reconstruct_path
from courier.io_utils import load_parcels
from courier.knapsack import format_dp_table, knapsack_01, knapsack_greedy_ratio
from courier.planner import STEP_NAMES, PlanConfig, candidate_window, plan_deliveries
from courier.tsp import build_distance_matrix, held_karp

HERE = os.path.dirname(os.path.abspath(__file__))


def banner(title):
    print("\n" + "=" * 78)
    print(f" {title}")
    print("=" * 78)


def run(args):
    parcels_path = args.parcels or os.path.join(HERE, "data", f"{args.dataset}_parcels.csv")
    edges_path = args.edges or os.path.join(HERE, "data", f"{args.dataset}_edges.csv")
    parcels = load_parcels(parcels_path)
    graph = Graph.from_csv(edges_path)
    cfg = PlanConfig(depot=args.depot, capacity_kg=args.capacity, speed_kmph=args.speed,
                     use_two_opt=not args.no_two_opt, vehicles=args.vehicles,
                     window_factor=args.window, cache_paths=not args.no_cache)
    verbose = args.verbose if args.verbose is not None else len(parcels) <= 20

    banner("MINI-COURIER PLANNER")
    print(f"Parcels file : {os.path.relpath(parcels_path, HERE)}  ({len(parcels)} parcels)")
    print(f"Graph file   : {os.path.relpath(edges_path, HERE)}")
    print(f"Depot={cfg.depot}  van capacity={cfg.capacity_kg} kg  speed={cfg.speed_kmph} km/h"
          f"  vans={cfg.vehicles}  window={cfg.window_factor or 'all'}  2-opt={'on' if cfg.use_two_opt else 'off'}")
    print(graph.describe())

    result = plan_deliveries(parcels, graph, cfg)

    # ---------------- Phase 2: sorting ----------------
    banner("PHASE 2a - PARCEL PRIORITISATION (merge sort: deadline asc, priority desc)")
    show = result.sorted_parcels if verbose else result.sorted_parcels[:15]
    print(f"{'#':>3} {'parcel':<7} {'dest':<6} {'kg':>4} {'prio':>5} {'deadline':>9} {'value':>6}")
    for i, p in enumerate(show, 1):
        print(f"{i:>3} {p.pid:<7} {p.destination:<6} {p.weight:>4} {p.priority:>5} "
              f"{p.deadline:>8}h {p.value:>6}")
    if len(show) < len(result.sorted_parcels):
        print(f"    ... {len(result.sorted_parcels) - len(show)} more")

    # ---------------- Phase 2: knapsack (first trip in detail) ----------------
    banner("PHASE 2b - BOX FILLING FOR TRIP 1 (0/1 knapsack DP)")
    candidates = candidate_window([p for p in result.sorted_parcels if p.weight <= cfg.capacity_kg],
                                  cfg.capacity_kg, cfg.window_factor)
    ks = knapsack_01(candidates, cfg.capacity_kg)
    if verbose:
        # every capacity column for normal vans; very large capacities are sampled
        print(format_dp_table(ks, candidates, max_cols=min(cfg.capacity_kg + 1, 61)))
        print()
    print(f"Optimal value = {ks.best_value}, weight used = {ks.total_weight}/{cfg.capacity_kg} kg")
    print("Selected parcels: " + ", ".join(p.pid for p in ks.chosen))
    g_val, g_set = knapsack_greedy_ratio(candidates, cfg.capacity_kg)
    print(f"(Greedy value/weight heuristic would get {g_val} -> DP gain "
          f"{ks.best_value - g_val})")

    # ---------------- Phase 3: graph + Dijkstra ----------------
    banner("PHASE 3a - SHORTEST PATHS FROM DEPOT (Dijkstra)")
    dist, prev = dijkstra(graph, cfg.depot)
    targets = sorted({p.destination for p in parcels}, key=lambda n: (dist[n], n))
    if not verbose:
        targets = targets[:10]
    for t in targets:
        print(f"  {cfg.depot} -> {t:<5} {dist[t]:>7.1f} km   path: "
              + " -> ".join(reconstruct_path(prev, cfg.depot, t)))

    # ---------------- Phase 3: trips ----------------
    banner("PHASE 3b - TRIPS AND ROUTES (nearest-neighbour TSP + 2-opt)")
    for trip in result.trips:
        print(f"\nTrip {trip.number}: {len(trip.parcels)} parcels, "
              f"{trip.total_weight}/{cfg.capacity_kg} kg, value {trip.total_value}, "
              f"van {trip.vehicle} departs at {trip.start_hour:.2f} h")
        print("  parcels   : " + ", ".join(p.pid for p in trip.parcels))
        print("  stop order: " + " -> ".join(trip.stop_order))
        print("  road path : " + " -> ".join(trip.full_path))
        print(f"  length    : {trip.route_km:.1f} km (nearest-neighbour {trip.nn_route_km:.1f} km)")
        if verbose:
            for s in trip.stops:
                ids = ",".join(p.pid for p in s.parcels)
                late = [p.pid for p in s.parcels if p in trip.late_parcels]
                flag = f"  LATE: {','.join(late)}" if late else ""
                print(f"     {s.node:<5} at {s.arrival_km:>6.1f} km, t={s.arrival_hour:>5.2f} h  [{ids}]{flag}")
        if len(trip.stop_order) - 2 <= 10:
            pts = list(dict.fromkeys(trip.stop_order))
            dm, _ = build_distance_matrix(graph, pts)
            opt, _ = held_karp(cfg.depot, pts, dm)
            print(f"  optimal (Held-Karp) = {opt:.1f} km -> NN ratio {trip.nn_route_km / opt if opt else 1:.3f}, "
                  f"final ratio {trip.route_km / opt if opt else 1:.3f}")

    # ---------------- summary ----------------
    banner("SUMMARY")
    print(f"Trips: {len(result.trips)}   total distance: {result.total_km:.1f} km")
    print(f"Delivered: {sum(len(t.parcels) for t in result.trips)}/{len(parcels)}   "
          f"late: {len(result.late)}   too heavy for van: {len(result.unassigned)}")
    if result.unassigned:
        print("Too heavy for the van: " + ", ".join(f"{p.pid} ({p.weight} kg)" for p in result.unassigned))
    if result.late:
        print("Late parcels: " + ", ".join(p.pid for p in result.late[:20])
              + (" ..." if len(result.late) > 20 else ""))
    print("\nRuntime of major steps (ms):")
    total = sum(result.timings.values()) or 1e-12
    for s in STEP_NAMES:
        ms = result.timings[s] * 1000
        print(f"  {s:<10} {ms:>9.3f} ms  ({100 * result.timings[s] / total:5.1f}%)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mini-Courier Planner")
    ap.add_argument("--dataset", choices=["small", "medium", "large"], default="small")
    ap.add_argument("--parcels", help="custom parcels CSV (overrides --dataset)")
    ap.add_argument("--edges", help="custom edges CSV (overrides --dataset)")
    ap.add_argument("--depot", default="D")
    ap.add_argument("--capacity", type=int, default=40, help="van capacity in kg")
    ap.add_argument("--speed", type=float, default=30.0, help="average speed km/h")
    ap.add_argument("--vehicles", type=int, default=1, help="number of vans")
    ap.add_argument("--window", type=float, default=0.0,
                    help="knapsack candidate window = WINDOW x capacity of most urgent parcels (0 = all)")
    ap.add_argument("--no-cache", action="store_true", help="disable the Dijkstra result cache")
    ap.add_argument("--no-two-opt", action="store_true", help="disable the 2-opt improvement")
    ap.add_argument("--verbose", dest="verbose", action="store_true", default=None)
    ap.add_argument("--brief", dest="verbose", action="store_false")
    ap.add_argument("--save", help="also write the trace to this text file")
    args = ap.parse_args(argv)
    try:
        _run_and_maybe_save(args)
    except (KeyError, ValueError, FileNotFoundError) as e:
        msg = e.args[0] if isinstance(e, KeyError) and e.args else e
        sys.exit(f"error: {msg}")


def _run_and_maybe_save(args):
    if args.save:
        buf = io.StringIO()
        with redirect_stdout(buf):
            run(args)
        text = buf.getvalue()
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(text)
        sys.stdout.write(text)
    else:
        run(args)


if __name__ == "__main__":
    main()
