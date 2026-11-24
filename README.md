# Polish national-road traffic map & network (GPR 2025)

A flow map of traffic on Poland's national roads (drogi krajowe): **line width ∝ SDRR**
(average annual daily traffic) from GDDKiA's *Generalny Pomiar Ruchu 2025*. It also builds
a **node/link network** with counts attached, ready to seed a national traffic model.

![cartogram](output/cartogram_2025_light.png)

## Status

_Updated 2026-11-24 (gap fixes, tighter map frame)_

- Pipeline rebuilt **section-first**: every GPR section is placed on the BDOT10k road graph
  by its own chainage (km). The old approach (`legacy/`) cut the network first and gave
  each piece the nearest counting point's value. In that version **369 sections (≈2,100 km)
  never showed their own value**: they took their neighbour's.
- **All 2,424 sections placed (18,364 km)**. 98.4% of km have a geometry length within
  ±20–25% of the official GPR length; median ratio 1.000. Only 56 sections still carry a
  `scale` flag (175 before the long-edge fix below).
- Roads that were not in operation in 2025:
  - BDOT10k roads with `KAT_ISTNIE ≠ eksploatowany` are drawn dashed and routed over only as a
    costly fallback (×2.5). BDOT lags reality: bits of S61, S11, S6, S19, S3, S7… that GPR counted
    in 2025 are still "w budowie" there and used to break those roads into pieces (visible gaps).
    About 140 km of such pieces now carry a counted section and are not drawn dashed.
  - GPR sections without counts carry `status`: `opened_after_count` (opened Dec 2025),
    `pending_2026` (supplementary count in 2026), `not_counted`.
  - National roads with no GPR section (mostly stretches managed by cities with county rights,
    plus old alignments) appear as grey lines and as `counted = false` links in the model network.
- 23 sections have their right/left counting points more than 1 km apart (two stations, or a
  wrong chainage). Their mean fell off the road and broke placement (e.g. A2 Łódź–Łowicz);
  step 01 now keeps the side consistent with the neighbouring sections (`side_used`).
- Gap fixes (2026-11-24), found with `output/qa_gaps.csv` (see step 05):
  - **Long BDOT features split into ≤250 m graph edges.** Anchors snap to graph nodes, and new
    expressways come as single 5–10 km features, so a counting point could snap kilometres away
    (S7 Gdańsk ring road, S51 Olsztyn …).
  - **Same-road holes healed**: up to 200 m on any road (e.g. S7 near Elbląg), up to 1 km on
    A/S roads, where BDOT sometimes leaves interchange cores unmapped (S6 at Węzeł Chwaszczyno
    is missing ~600 m).
  - **Gap closing**: an open stretch of the same road between loose ends of two sections
    (or two parts of one section) is split between them (`qa_flags` `gap_closed`). On A/S
    roads, a stub of up to 1 km from a loose section end into an interchange with another road
    is added to that section (the S7 link into the S6 at Chwaszczyno). This mostly
    happens where one chainage system hands over to the next. A/S up to 25 km; DK only up to 2 km
    and never next to a city-limit section.
  - What is left in `qa_gaps.csv` (74 stretches, 337 km): mostly city-managed roads and old
    alignments left behind when a DK moved onto a bypass or an S-road.
- Model network: 2,896 nodes, 3,466 links (2,985 counted, 481 uncounted ≈1,610 km),
  99.6% of nodes in one connected component.
- BDOT10k re-extracted 2026-11-24 with all attributes (92,636 features, 739 under construction).
  Mazowieckie ships its layer in two parts (`*_SKDR_L.shp` + `*_SKDR_L_1.shp`); step 00 reads both.
- See `output/qa_report.md` for current metrics and `output/qa_sections_to_review.csv`
  for flagged sections.

## Outputs (`output/`)

| file | what |
|---|---|
| `traffic_network_2025.gpkg` | **main product** (EPSG:2180). It has QGIS default styles embedded, so drag it into QGIS |
| ├ `sections` | one line per GPR section: SDRR, vehicle classes, heavy share, status, QA |
| ├ `links`, `nodes` | modelling topology (sections split at junctions + uncounted connectors) |
| ├ `counting_points` | GPR counting stations |
| ├ `skdr_unmeasured` | operational national roads not covered by a section |
| └ `skdr_not_operational` | BDOT10k national roads under construction |
| `links_2025.csv`, `nodes_2025.csv` | the same topology as plain tables (from/to node, SDRR, km) |
| `cartogram_2025_light.png` / `_dark.png` | rendered flow map |
| `gpr2025_sections.csv`, `gpr2025_pieces.csv` | parsed GPR tables (sections; per-chainage-system pieces) |
| `qa_report.md`, `qa_sections_to_review.csv`, `qa_gaps.csv` | quality metrics; uncovered stretches between sections |

## Pipeline (`pipeline/`)

Run everything: `.venv\Scripts\python.exe pipeline\run_all.py` (about 2 min).
Add `--extract` to re-extract BDOT10k first (about 1 h; only after a new BDOT download).

| step | does |
|---|---|
| `00_extract_bdot.py` | national roads (`OT_SKDR_L`, `KAT_ZARZAD=krajowa`) from `Polska_SHP.zip`, all attributes, full resolution → `data/bdot/skdr_krajowe.gpkg` |
| `01_parse_gpr.py` | GPR Tab01+Tab02 → sections + **pieces** (one per chainage system), status from remarks |
| `02_build_graph.py` | BDOT10k lines → routable graph (edges ≤250 m, healed between sheets and across short same-road holes; 'w budowie' as costly fallback) |
| `03_locate_sections.py` | **linear referencing** of sections (see below) |
| `04_build_network.py` | nodes/links: cluster section ends, split at T-junctions and at-grade crossings, add uncounted connectors |
| `05_qa_report.py` | metrics → `qa_report.md`, visible gaps → `qa_gaps.csv` |
| `06_render_cartogram.py` | PNG maps (light/dark) |
| `07_style_qgis.py` | `.qml` styles in `qgis/` and default styles embedded in the GeoPackage |

Shared settings: `pipeline/config.py`. Helpers: `pipeline/common.py`.

### How sections are placed (step 03)

GPR's `nr_drogi` is a **chainage system**, not just a road. `S7j`, `94g` and `A1c` each have
their own km numbering, and 226 sections span two systems (`A1d\nA1c`, with two km ranges).
For each system:

1. Split into **runs** of contiguous km (gaps > 1 km are stretches renumbered to other roads).
2. **Anchors** are counting points: their km (`pik_prawy`/`pik_lewy`) and position are both known.
3. Route between consecutive anchors on the SKDR graph, preferring edges with the same road
   number (cost ×1.0; same number but other class ×1.3; other road ×3; any "w budowie" edge
   ×2.5 on top). Anchors snap to operational edges first. km → metres is
   interpolated piecewise-linearly between anchors, which absorbs GDDKiA-vs-BDOT length
   differences locally.
4. If a route is implausible (more than 2× the km difference, typically a through-town
   stretch missing in BDOT), the run is split into chains and each is extended to the midpoint.
5. Before the first and after the last anchor, extend along the graph by the remaining km,
   heading away from the neighbouring anchor.
6. Cut every piece `[pik_pocz, pik_konc]` from the run line. Pieces with no anchor are
   placed from coordinates (`loose`) or attached to the adjacent piece of the same section.
7. Close gaps: an open stretch of the same road left between the loose ends of two sections
   is split between them (`gap_closed`).

QA columns on `sections`: `placement` (strict/loose/attached), `qa_flags`
(scale, chain_break, clipped, foreign, partial, gap_closed), `geom_km`, `len_ratio`.

### Network topology (step 04), known limits

- Section ends within 350 m become one node (interchanges and ramps fall within that).
- A node within 300 m of another section's interior splits that section (T-junction).
- Mid-section crossings: DK×DK are connected (at grade); crossings involving an A or S road
  only if an operational BDOT10k interchange (`skrw_wezly`) lies within 1 km. Otherwise
  they are treated as overpasses.
- Links are undirected, and lanes and speeds are not attached yet. For a model, the next
  step is adding regional roads (`skdr_wojewodzkie`) and zone connectors.

## Data

- `data/raw/` holds GDDKiA GPR tables: 2025 (`Tab01/02_25_…xlsx`), 2020/21 (`.xls`) and
  2015 (PDF).
- BDOT10k (GUGiK) comes from `D:\QGIS\BODT10k\Polska_SHP.zip`, with interchanges in
  `D:\QGIS\BODT10k\SKDR\skrw_wezly.gpkg` and admin boundaries in `granice_admin.shp`.
  These are not in the repo because of their size.

## Environment

Python 3.8 venv in `.venv` (see `requirements.txt`). Keep `fiona<1.10` with geopandas 0.13.
The C: drive is nearly full: keep temp and large files on D:.

## Next ideas

- Historical comparison: parse GPR 2020/21 (`odcinek_gpr2020` links sections 1:1) and 2015 (PDF).
- Traffic model: add regional roads and gminas as zones, then calibrate a gravity model
  against `links.sdrr_total`.
- Interactive web map (sections as GeoJSON, about 2,400 features).

## Legacy

`legacy/` holds the first approach (cut network at junctions, nearest counting point wins)
and its QGIS project `gpr-map.qgz`. It is kept for reference; outputs in `legacy/output/`
are not in git.
