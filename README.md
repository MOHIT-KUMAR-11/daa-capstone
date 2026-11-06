# Mini-Courier Planner

**Capstone Assignment: Design & Analysis of Algorithms (ETCCDA302)**
K.R. Mangalam University, B.Tech CSE

**Student:** _your name_ · **Roll no.:** _your roll number_ · **Faculty:** Dr. Shweta Agarwal

You give it a list of parcels and a city road map. It produces an ordered delivery route and an
optimized packing plan. Four algorithm families work together:

| Step | Algorithm | File |
|---|---|---|
| Prioritise parcels | Merge sort (also insertion, quick and heap sort for comparison) | [`courier/sorting.py`](courier/sorting.py) |
| Fill the van | 0/1 knapsack with dynamic programming | [`courier/knapsack.py`](courier/knapsack.py) |
| Shortest paths | Dijkstra (binary heap) on an adjacency-list graph | [`courier/graph.py`](courier/graph.py) |
| Delivery route | Nearest-neighbour TSP + 2-opt (Held-Karp exact DP used to check quality) | [`courier/tsp.py`](courier/tsp.py) |
| Integration | Multi-trip, multi-van planner with deadline check | [`courier/planner.py`](courier/planner.py) |

Only the Python standard library is needed (tested on Python 3.13) to run the planner. `matplotlib` is needed only to redraw the charts.

---

## Documentation

| Phase | Document |
|---|---|
| 1. Problem design and planning | [`docs/DESIGN.md`](docs/DESIGN.md) |
| 2–5. Results, testing, optimisation, demonstration | [`docs/REPORT.md`](docs/REPORT.md) |
| Output traces | [`results/trace_small.txt`](results/trace_small.txt), [`trace_medium.txt`](results/trace_medium.txt), [`trace_large.txt`](results/trace_large.txt) |
| Runtime data and charts | [`results/`](results/) (`bench_*.csv`, `chart_*.png`) |
| Screenshots | [`screenshots/`](screenshots/) |

## Project layout

```
mini-courier-planner/
├── main.py                  # command-line app (runs the whole pipeline, prints the trace)
├── benchmark.py             # Phase 4: runtime tests + charts
├── courier/
│   ├── models.py            # Parcel / Trip / Stop data classes
│   ├── sorting.py           # insertion, merge, quick, heap sort
│   ├── knapsack.py          # 0/1 knapsack DP (+ brute force, greedy, O(W) version)
│   ├── graph.py             # Graph (adjacency list), Dijkstra, Floyd-Warshall
│   ├── tsp.py               # distance matrix, nearest neighbour, 2-opt, Held-Karp
│   ├── planner.py           # integrates every step, timing of each step
│   ├── io_utils.py          # CSV loading/saving
│   └── generator.py         # reproducible random datasets
├── data/                    # small (hand-made), medium, large datasets
├── tests/test_algorithms.py # 19 correctness tests
├── tools/                   # draw graph picture, render screenshots
├── results/                 # traces, benchmark CSVs, charts
├── screenshots/             # output screenshots used in the report
└── docs/                    # DESIGN.md (phase 1), REPORT.md (phases 2–5)
```

## Execution steps

```bash
git clone <this-repo-url>
cd mini-courier-planner
```

```bash
python -m pip install -r requirements.txt
```

1. **Run the planner on the small dataset.** This prints the full trace: sorted list, DP table, Dijkstra paths, routes and timings.

   ```bash
   python main.py
   ```

2. **Medium and large datasets** (several vans):

   ```bash
   python main.py --dataset medium --capacity 60 --vehicles 3
   ```

   ```bash
   python main.py --dataset large --capacity 120 --vehicles 10 --brief
   ```

3. **Your own (unseen) dataset.** Use the same CSV columns as the files in `data/`:

   ```bash
   python main.py --parcels my_parcels.csv --edges my_edges.csv --depot D --capacity 50
   ```

4. **Run the correctness tests:**

   ```bash
   python -m unittest discover -s tests -v
   ```

5. **Run the performance tests and redraw the charts** (about 1–2 minutes):

   ```bash
   python benchmark.py
   ```

6. Optional: regenerate the datasets, the graph picture and the screenshots:

   ```bash
   python -m courier.generator
   ```

   ```bash
   python tools/draw_small_graph.py
   ```

   ```bash
   python tools/render_screenshots.py
   ```

### Command-line options

| Option | Default | Meaning |
|---|---|---|
| `--dataset {small,medium,large}` | small | bundled dataset |
| `--parcels FILE` / `--edges FILE` | – | custom CSV files (override `--dataset`) |
| `--depot` | D | depot node id |
| `--capacity` | 40 | van capacity in kg |
| `--vehicles` | 1 | number of vans |
| `--speed` | 30 | average speed, km/h |
| `--window K` | 0 (off) | knapsack sees only the most urgent parcels, up to K × capacity (optimisation) |
| `--no-two-opt` | – | use the plain nearest-neighbour route |
| `--no-cache` | – | recompute Dijkstra for every trip (turns off the shortest-path cache) |
| `--verbose` / `--brief` | auto | full trace (DP table, every stop) or summary |
| `--save FILE` | – | also write the trace to a text file |

## Input format

`parcels.csv`

```
parcel_id,destination,weight_kg,priority,deadline_hr
P01,C1,8,5,2
```

`edges.csv` (two-way roads)

```
from,to,distance_km
D,C1,4
```

## Result on the small dataset (van capacity 40 kg)

![routes](results/small_graph_routes.png)

* 12 parcels (92 kg) need **3 trips**. Trip 1 carries 7 parcels, 38 kg, with knapsack value 391.
* Trip 1 route `D → C3 → C6 → C8 → C5 → C4 → C1 → D` is **35 km**. Nearest neighbour alone gave
  43 km, so 2-opt saved 18.6%. The exact Held-Karp optimum is also 35 km.
* All 12 parcels arrive on time, and the total distance is 101 km.

The full analysis is in [`docs/REPORT.md`](docs/REPORT.md).
