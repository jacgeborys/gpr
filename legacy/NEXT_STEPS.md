# Poland Traffic Cartogram — Handoff Notes
_For the next Claude Code session. Working dir: `D:\QGIS\gpr`_

---

## Goal

Build a **traffic flow map** of Poland's national roads using GPR (Generalny Pomiar Ruchu) 2025 data — road line widths proportional to SDRR (average annual daily traffic).

---

## Current status — pipeline is working, ~96% matched

The main output is `output/roads_gpr2025.gpkg`, layer `roads_gpr2025`:
- **3,175 road segments**, ~95.9% matched with SDRR
- Key columns: `road_key`, `sdrr_total`, `gpr_odcinek`, `dist_to_gpr_m`,
  `join_method` (nn_close / nn_near / nn_far / unmatched / dummy),
  `wezly_od` / `wezly_do` (interchange names for A/S roads), `seg_type`

### Scripts
| # | Script | Purpose |
|---|--------|---------|
| 01 | `01_parse_gpr2025.py` | Parse Excel → `output/gpr2025.csv` + `gpr2025.gpkg` |
| 02 | `02_join_skdr_gpr2025.py` | Exploratory (not critical) |
| 03 | `03_build_graph.py` | **Main**: segment roads at junctions, assign SDRR |
| 04 | `04_make_s7_preview.py` | Optional S7 preview |
| 05 | `05_orphaned_gpr.py` | GPR points with no matching road edge → `output/orphaned_gpr.csv` |
| 06 | `06_orphaned_edges.py` | Road edges with no SDRR, sorted by length → `output/orphaned_edges.csv` |

### Virtual environment
`D:\QGIS\gpr\.venv` — Python 3.8, geopandas 0.13.2, shapely 2.0.7, **fiona 1.9.6** (pinned <1.10)
Run with: `D:\QGIS\gpr\.venv\Scripts\python.exe <script>`

---

## Immediate next task — fix unmatched edges and orphaned GPR points

### Step 1: Understand the DK9 bug (highest priority)

All 188.7 km of DK9 is unmatched despite 33 GPR points existing for road `9`.
The suspected cause: **very long edges** (some are 40–47 km). The SDRR assignment
in `03_build_graph.py` uses the geometric **centroid** of each edge to find the
nearest GPR point. For a 47 km edge, the centroid is at the midpoint — if GPR points
cluster near one end, the centroid can be >20 km away, hitting the `MAX_SDRR_DIST_M`
cap and leaving the edge unmatched.

**Fix to implement in `03_build_graph.py` step 9 (Assign SDRR)**:
Instead of using just the edge centroid, sample multiple points along the edge
(e.g. every 5 km or at 25%, 50%, 75% positions) and use the minimum distance
to any sample point when deciding which GPR point to assign.

### Step 2: Analyse all unmatched edges

Run `06_orphaned_edges.py` on fresh output and inspect `output/orphaned_edges.csv`.
Classify each road's gap as one of:
- **Bug** (like DK9) — road and GPR data exist but matching fails
- **GPR gap** — no measurement points on that section (intentional)
- **SKDR gap** — road geometry missing from BDOT10k for that section

Current unmatched km by road (before DK9 fix):
```
9     188.7 km  ← known bug
3      89.3 km
7      61.4 km
A2     55.3 km
18     51.4 km
6      46.1 km
61     43.1 km
S19    42.1 km
79     24.4 km
8      18.8 km
19     16.2 km
11     11.0 km
89     10.6 km
1       9.6 km
2       7.7 km
```

### Step 3: Analyse orphaned GPR points

Run `05_orphaned_gpr.py` and inspect `output/orphaned_gpr.csv`.
Currently 10 orphaned points. Known issues:
- Road `9` (7 points) — affected by the DK9 matching bug above
- Road `5r` (1 point, SDRR 2170) — isolated counting station, nothing in SKDR nearby, leave as-is
- Roads `2b` and `6` — already handled by existing numeric fallback (A2 picks up `2`, S6 picks up `6`), `05_orphaned_gpr.py` incorrectly flags these

---

## Segmentation logic (for reference)

- **A/S roads**: cut at named interchange points (NAZWA_WEZL NOT NULL), 596 interchanges, snap within 500 m
- **National roads**: Pass 1 = krajowe×krajowe geometric intersections; Pass 2 = refine at GPR section boundaries using nearest woj→pow→midpoint crossing
- Carriageway deduplication: centroids within 60 m + length ratio >50% → drop shorter
- SDRR assignment: `sjoin_nearest` on edge centroids to same-road GPR points, capped at `MAX_SDRR_DIST_M = 20_000`
- Numeric fallback: `A2`/`S2` edges also search GPR road_key `2`; does NOT go the other direction

---

## Future work (lower priority)

- Historical comparison with GPR 2020: `Tab01_20_dk_KRAJ.xls` / `Tab02_20_dk_KRAJ.xls`
- GPR 2015 PDF extraction: `WYKAZ_GPR2015_DK.pdf` / `WYNIKI_GPR2015_DK.pdf`

---

## Environment notes

- **C: drive is tight** — always use `D:` for temp/large files
- pip cache safe to delete: `C:\Users\Asus\AppData\Local\pip\cache`
- fiona must stay pinned to `<1.10` in the venv (1.10+ breaks geopandas 0.13.2)
