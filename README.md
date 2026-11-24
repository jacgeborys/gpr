# Polish national-road traffic map & network (GPR 2025)

A flow map of traffic on Poland's national roads (drogi krajowe): **line width ∝ SDRR**
(average annual daily traffic) from GDDKiA's *Generalny Pomiar Ruchu 2025*. It also builds
a **node/link network** with counts attached, ready to seed a national traffic model.

![cartogram](output/cartogram_2025_light.png)

## Status

_Updated 2026-11-24_

- **All 2,424 GPR sections placed (18,364 km), and the network is continuous**: the model
  network has 99.5% of its nodes in one component, and 60 dead ends more than 3 km from the
  border (`qa_dead_ends.csv`, mostly real road ends and uncounted city connectors).
- How sections are drawn (details below):
  1. **Placement (step 03)**: each section is placed by its own chainage (km) on a routable graph
     of BDOT10k national roads, patched with **OpenStreetMap** main roads where BDOT has holes
     (unmapped interchange cores, roads opened after the BDOT update).
  2. **Stitching (step 03b)**: section ends are then tied together along roads: consecutive
     sections of one chainage system, sections named after the same interchange, and any ends
     closer than 350 m. Continuity takes priority over the exact alignment inside interchanges or
     whether traffic uses an old or a new alignment (e.g. DK8 Suchowola–Białystok).
- Fixes along the way: long BDOT features split into ≤250 m edges (anchors snapped kilometres
  off on new expressways); same-road holes healed (≤200 m, A/S ≤1 km); counting points with
  right/left sides kilometres apart; points up to 1 km outside their section; one-anchor runs
  and extensions that turned back; BDOT "w budowie" used as fallback, and freely for roads
  opened in 2025.
- Roads not open in 2025: BDOT "w budowie" is drawn dashed. GPR `status` marks sections opened
  after the count (`opened_after_count`) or counted in 2026 (`pending_2026`), drawn dotted.
  Closed OSM ways (`access=no`, `construction`) are never used. **S19 at Boćki**: the S19 section
  ends at Węzeł Boćki (built S19 further south was closed in 2025), and DK19 continues south from
  there (rule: a section is cut where a section of another road starts at the same-named
  interchange, `qa_flags` `trimmed`).
- Map: 9 SDRR colour classes (light: yellow → red → purple; dark: blue → pink → yellow), width ∝ SDRR;
  roads without counts in a grey between the land colour and the lowest class; font
  Bahnschrift. QGIS default styles in the GeoPackage use the same classes.
- Model network: 2,663 nodes, 3,179 links (2,787 counted, 392 uncounted ≈1,360 km).

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
| `qa_report.md`, `qa_sections_to_review.csv`, `qa_gaps.csv`, `qa_dead_ends.csv` | quality metrics; uncovered stretches between sections |

## Pipeline (`pipeline/`)

Run everything: `.venv\Scripts\python.exe pipeline\run_all.py` (about 2 min).
Add `--extract` to re-extract BDOT10k first (about 1 h; only after a new BDOT download).

| step | does |
|---|---|
| `00b_fetch_osm.py` | OSM motorway/trunk/primary (+ links) from Geofabrik `poland-latest.osm.pbf` (`config.OSM_PBF`) → `data/osm/osm_main_roads.gpkg`; run with `run_all.py --osm` |
| `00_extract_bdot.py` | national roads (`OT_SKDR_L`, `KAT_ZARZAD=krajowa`) from `Polska_SHP.zip`, all attributes, full resolution → `data/bdot/skdr_krajowe.gpkg` |
| `01_parse_gpr.py` | GPR Tab01+Tab02 → sections + **pieces** (one per chainage system), status from remarks |
| `02_build_graph.py` | BDOT10k lines → routable graph (edges ≤250 m, healed between sheets and across short same-road holes; 'w budowie' as costly fallback) |
| `03_locate_sections.py` | **linear referencing** of sections (see below) |
| `03b_stitch_network.py` | make the network continuous: join consecutive / same-interchange / nearby section ends along roads (`stitched`), tie loose ends onto nearby lines |
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
