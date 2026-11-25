# Polish national-road traffic map & network (GPR 2025)

A flow map of traffic on Poland's national roads (drogi krajowe): **line width ∝ SDRR**
(average annual daily traffic) from GDDKiA's *Generalny Pomiar Ruchu 2025*. It also builds
a **node/link network** with counts attached, ready to seed a national traffic model.

![cartogram](output/cartogram_2025_light.png)

## Status

_Updated 2026-11-24_

- **All 2,424 GPR sections placed (18,364 km), and the national network is continuous**
  (`qa_dead_ends.csv` lists the remaining dead ends).
- How sections are drawn (details below):
  1. **Placement (step 03)**: each section is placed by its own chainage (km) on a routable graph
     of BDOT10k national roads, patched with **OpenStreetMap** main roads where BDOT has holes
     (unmapped interchange cores, roads opened after the BDOT update).
  2. **Stitching (step 03b)**: section ends are then tied together along roads: consecutive
     sections of one chainage system, sections named after the same interchange, and any ends
     closer than 350 m. Continuity takes priority over the exact alignment inside interchanges or
     whether traffic uses an old or a new alignment (e.g. DK8 Suchowola–Białystok).
- **Gaps only at cities** (checked 2026-11-24): the 66 cities with powiat rights are drawn as
  pale areas (OSM boundaries, step 00b `cities`). Outside them, uncounted national road left on
  the map is ≈47 km in 12 stretches: old roads into towns that GDDKiA now routes around
  (old DK20 through Szczecinek, old DK63/DK61 into Łomża) and sub-2 km interchange bits.
  What made this work:
  - **Interchange anchors**: section ends named 'W. <name>' are matched to OSM
    `motorway_junction` names (PŁD./PŁN./WSCH./ZACH. expanded, other abbreviations as prefixes;
    1,471 of 1,637 ends) and anchor the section's start/end km. At a shared km a section's end
    comes before the next one's start (DK20 → S11 → DK20 at Szczecinek).
  - **Road hints in names** ('W. LATKOWO /DK15/'): a one-anchor run must end near the named road;
    both directions are tried for each side.
  - **Stitching extras**: loose ends paired along roads (≤8 km), loose ends followed along their own
    road number to the network (≤8 km, jumping BDOT holes ≤600 m), consecutive sections always
    joined; DK dead ends may join an A/S interchange within 600 m in the graph.
  - **Parallel old alignments dropped** from context and model: an uncounted chain entirely within
    2.5 km of a counted route of the same number (or of an A/S road when its own number has no
    count within 10 km); city through-roads are kept for routing.
- Fixes along the way: long BDOT features split into ≤250 m edges (anchors snapped kilometres
  off on new expressways); same-road holes healed (≤200 m, A/S ≤1 km); counting points with
  right/left sides kilometres apart; points up to 1 km outside their section; one-anchor runs
  and extensions that turned back; BDOT "w budowie" used as fallback, and freely for roads
  opened in 2025.
- Roads not open in 2025: GPR `status` marks sections opened after the count
  (`opened_after_count`) or counted in 2026 (`pending_2026`), drawn dotted in the no-data grey.
  BDOT "w budowie" is no longer drawn (layer `skdr_not_operational` is kept in the GeoPackage).
  Closed OSM ways (`access=no`, `construction`) are never used. **S19 at Boćki**: the S19 section
  ends at Węzeł Boćki (built S19 further south was closed in 2025), and DK19 continues south from
  there (rule: a section is cut where a section of another road starts at the same-named
  interchange, `qa_flags` `trimmed`). S10 south of Toruń (being widened) is drawn in full.
- Downgraded old alignments are dropped from the uncounted context and the model: an uncounted
  DK N stretch with a counted S N section within 20 km and no counted DK N section within 10 km
  (DK61 north of Ostrów Maz. now that S61 is open, old DK19 Bielsk–Boćki), and national-road
  pieces BDOT lists without a number (≈250 km).
- **Regional roads (drogi wojewódzkie)** from BDOT10k (`config.DW_GPKG`, ≈29,700 km) are in
  the model network as uncounted links (`road` = `DW<number>`, `road_class` = `DW`) and on the
  map as thin context. GPR 2025 data here covers national roads only, so they have no counts.
- Map: 9 SDRR colour classes (light: yellow → red → purple; dark: blue → pink → yellow), width ∝ SDRR;
  roads without counts in a grey between the land colour and the lowest class; font
  Bahnschrift. QGIS default styles in the GeoPackage use the same classes.
- Model network: 6,704 nodes, 8,484 links (3,296 counted; 5,188 uncounted ≈30,700 km, mostly
  regional roads); 97.4% of nodes in one component. Dead ends > 3 km from the border: 34 on
  national roads, 590 on regional roads (they often end in towns).

### GPR 2025 regional roads (work in progress)

`set GPR_NET=dw` (config.NET) runs the 2025 steps on the regional tables
(`Tab01_25_dw_KRAJ.xlsx`, `Tab02_25_dw_KRAJ.xlsx`: 3,305 sections, 3,263 with SDRR, one counting
point each with coordinates) into separate files (`gpr2025_dw_*`, `skdr_graph_2025_dw.pkl`,
`traffic_network_2025_dw.gpkg`). Step 02 builds the graph from BDOT regional roads plus the
national ones (a regional section may run over a shared stretch); 'unmeasured' counts only the
regional roads. Status 2026-11-25: 3,262 of 3,305 sections placed (27,942 of 28,171 km; the
43 left are mostly without SDRR or with no usable km/point), 2,671 with no QA flag. Step 03 takes
~2 min but needs most of the 16 GB (close other programs). Map: `06_render_cartogram.py --dw`
(GPR_NET unset) draws national + regional sections on one scale →
`output/cartogram_2025_dkdw_{light,dark}.png`; the national-only map is unchanged.
Legend (all maps): one entry "drogi bez danych (głównie odcinki w miastach)" for every road
without data (national and regional); dotted "odcinki bez pomiaru w 2025" (GPR sections opened after the count or recounted in
2026) only where such sections exist (2025: 22 sections, 134 km); cities with powiat
rights keyed by an irregular blob, not a bar.
**Truck maps** (`06_render_cartogram.py --dw --trucks`; trucks = samochody ciężarowe bez + z
przyczepą, buses and vans not included): `cartogram_2025_dkdw_trucks_*.png`, where width ∝ SDRR in blue
with a red core whose width is the truck share of that line (lines drawn in chunks, each
chunk's lines then their cores, so thin roads' cores don't cross motorways; cores are one flat
red without anti-aliasing, and cores under `CORE_MIN_PT` = 0.45 pt are not drawn because they
would blend into purple), and
`cartogram_2025_dkdw_truckshare_*.png`, where width ∝ SDRR and colour = truck share
(<5 / 10 / 15 / 20 / 30 / >30 %, blue → red). The current share ramp barely changes lightness,
so its middle classes merge for red–green colour-blind readers. Candidate ramps with a lightness
step (`TRUCK_SHARE_VARIANTS` A/B/C/D, D = current ends with re-spaced middle classes; `--dw --ramp X` → `..._truckshare_X_*.png`, not committed)
were tried; the current ramp was kept (2026-11-25): the vivid middle hues that make it look good are the same ones that merge, and the alternatives look duller. Median truck share: 12% on national roads,
5% on regional roads.
**English versions**: add `--lang en` (all map modes) → same file names ending in `_en`
(AADT for SDRR, "cities with county rights", Warszawa → Warsaw; numbers with comma separators).
Not yet: 03b stitching for regional sections, a closer look at the 'foreign' / 'scale' flags.

### GPR 2010 regional roads

Regional roads barely changed course since 2010 and mostly kept their km, so they are placed
on today's roads by km instead of reading the dense regional PDF map:
1. `01_parse_gpr2010_dw.py` — table `0116_SDR_drwoj_w_pkt_pomiarowych_w_2010_roku.pdf` →
   `output/gpr2010_dw_sections.csv` (2,796 sections on 790 roads, 2,790 with SDR; the other 6
   have none in the source). Read char by char: the bold voivodeship heading printed over some
   rows is dropped by font, numbers are digit runs snapped to the right-aligned column edges,
   and an overflowing name's digits are cut off the total by checking the class sum.
2. `03_place_dw2010.py` — each section's km range is cut out of the 2025 regional sections of
   the same road (`traffic_network_2025_dw.gpkg`, km ↔ distance piecewise linear) →
   `output/traffic_network_2010_dw.gpkg`. 2,585 placed (25,576 of 26,853 km), 123 with length
   ratio outside 0.67–1.5 (flag 'scale'); 211 unplaced (roads no longer regional, or km outside
   the 2025 coverage) → `output/gpr2010_dw_unplaced.csv`.
3. `06_render_cartogram.py --dw` with GPR_YEAR=2010 → `output/cartogram_2010_dkdw_*.png`.
Next: recover the unplaced 211 (km shifts, name anchors), check the 'scale' ones.

### GPR 2010 (work in progress)

Current method (`set GPR_YEAR=2010`):
1. `01_parse_gpr2010.py` — Tablica 1 + 2 PDFs (`data/raw/2010/`) → `output/gpr2010_sections.csv`
   (1,792 sections, all with SDR; counting points located by 2025 km or by locality name).
2. `03_pdf_sections2010.py` — geometry from GDDKiA's own `Mapa_SDR2010.pdf`: every section is one
   grey vector line (1,787 on the main map; the Górnośląski inset edge and the legend are left
   out), georeferenced by ICP against BDOT (median 82 m). The parsed PDF is cached in
   `output/pdf2010_cache.pkl` (delete it after changing the PDF parsing; rebuild ~3 min).
   - **Labels** (`pdf_labels2010.py`): glyph outlines → clusters by outline gap → every straight
     run of glyphs is read (touching digits are cut, digits classified by nearest neighbours in
     `data/label_templates2010.npz`, a bank of digit rasters taken from the map's own confident
     reads), and decoded against the SDR values of sections whose counting point is near; the
     longest runs that read as a table value win. 1,441 labels, ~1,410 exact on a line.
   - **Counting points fixed from the map**: a section whose (unique) value is read on the map
     gets the label position when it had no point or a locality point > 25 km away (a namesake
     village); else from its km-neighbours (also replaces locality points > 60 km off).
   - **Assignment** (Hungarian) on counting-point distance, length, green band width, labels
     (exact read near the point −120; a line read as a unique value is reserved for it, +80 for
     others; a far read counts if a km-neighbour's value is read on a touching line) and
     continuity (Viterbi over touching lines). A section may stay off the map (cost 40) rather
     than fill a far line; then a **repair** pass puts such sections on empty lines touching
     their km-neighbour's line, and moves *stranded* sections (line touches none of their
     km-neighbours' lines, no label confirms it, e.g. a namesake-village point) to such an empty
     line if it fits the length about as well. km-neighbours link a road and its expressway on
     the same chainage (DK7 → S7 at Grójec, DK8 → S8 at Radzymin). Empty lines are drawn as roads
     without a count.
3. `03c_real_shapes2010.py` — real road shapes: every map line is traced onto today's national
   + regional roads (BDOT10k, `config.SKDR_GPKG` + `config.DW_GPKG`). Touching line ends form a
   junction with one road node (nearest to all incident lines, real junctions preferred), so
   traced lines meet without gaps; between its two nodes a line takes the cheapest path, an
   edge costing length × (1 + (distance from the map line / 400 m)²) — where the 2010 road is
   regional now (a parallel A/S road took the traffic) the regional road is closer and wins.
   Holes in the road data are bridged by straight jumps ≤ 1 km (5× cost). Kept only within
   2.5 km of the map line and 0.7–1.8× its length; otherwise the PDF shape stays (ends snapped
   to the junction nodes), column `shape` = road / pdf. Where the national + regional trace
   is > 250 m from the map line on average, county roads (BDOT `skdr_powiatowe.gpkg`, 1.2×
   cost) are tried too and win if ≥ 30% closer: old routes demoted below regional (old DK17
   NW of Lublin, next to today's S17). A trace sharing > 25% of its length with other
   sections' traces is retraced with those roads costing 4× (Garwolin bypass 2 had followed
   Rębków–Garwolin before turning south). 97% of the length is traced. Traces and road pieces
   are cached (`output/trace_cache_2010.pkl`, `roads_cache_2010.pkl`): the first run ~30 min,
   re-runs only trace lines that changed.
   Writes `sections` / `skdr_unmeasured` with real shapes, keeps the map shapes as
   `sections_pdf` / `unmeasured_pdf` (step 08 uses those) and adds `regional_roads`.
   Re-running step 03 overwrites the gpkg: run 03c after it.
4. `06_render_cartogram.py` → `output/cartogram_2010_*.png`.
5. `08_suspects2010.py` — QA: lists suspects (`output/qa_suspects2010.csv`: label read on the line
   ≥ 2 edits from its value; >2× jump against all same-road neighbours; short high line) and
   draws `output/debug2010/NNN_<section>.png` (left: GDDKiA map crop, right: ours with values and
   label reads). `--at lon,lat ...` draws ad-hoc windows (`at_N.png`).

Status (2026-11-24): fixed DK63 near Wisznice, the Wrocław value in Inowrocław, DK8 sections
dropped in Marki/Jędrzejów/Kozienice, S7 on DK8 at Mszczonów, Dębica, Sieradz, Oleśnica. The 21
remaining suspects were checked by eye: label flags are misreads in crowded junctions with a
correct value, jump/short-high flags are real short town crossings (PRZEJŚCIE).
2026-11-25: 40205 Koziegłowy–Siewierz (DK1) was lost by the table grid (merged cells) — step 01
now parses such rows from the page text (1,793 sections). Stranded-section moves fixed DK2
Mińsk–Kałuszyn, A2 Buk–Komorniki, Miechów, Żyrardów–Korytów; S-road neighbours placed the Grójec
bypass and DK8 Marki.
Then the last 13 off-map sections were debugged one by one:
- the page cut for the insets was at x 1150, but the main map's west edge reaches x ≈ 1080:
  DK10 Lubieszyn–Szczecin and DK26/31 around Chojna were not read at all. Now MAIN_X = 1000
  (Warsaw/Poznań insets end at ≈ 996; the Górnośląski inset is a NOT_MAIN box) and the ICP fit
  leaves the boxes out;
- labels between two parallel lines: when a line gets exact labels of two values, the one whose
  section length fits the line stays, the other moves to the nearest unlabelled line (fixed
  A4a Godzieszów–Bolesławiec and S7 at Białobrzegi, where the 1.2 km DK48 crossing's 5934 had
  taken the 10 km S7 line);
- labels also carry the direction of their digits; when two labels compete for one line, the
  one written across it wins ties (DK4 / DK77 at Jarosław). Only a tie-breaker: GDDKiA does not
  always write values across the road (Skarżysko-Kam.);
- a leftover section may also take an empty line that continues its road number and fits its
  length within 1.2× (S11 W. Kórnik Płd.–Środa Wlkp. between two DK11 lines);
- a unique 5-digit label on a line of the right length overrides a far 2025-chainage point
  (DK11 at Ostrów Wlkp.: the chainage changed with S11);
- `leftover()`: sections with no usable point (bypasses of Prudnik / Opole, Lubin–Ścinawa,
  Sławno–Słupsk, Wrocław–Bielany stub) take an empty line of their length within 8 km of a
  place named in the section name; and a section takes a line held by one whose named towns
  are all > 25 km away (Tomaszów Maz. bypass had "Piaski bypass" — a namesake-village point;
  Piaski then took its own empty line near Lublin).
1,792/1,793 sections on the map, no grey line; 12 suspects left, all checked by eye (misreads
at crowded junctions, real short town crossings). Off the map: DK25 Nowe Skalmierzyce crossing
(4.1 km) — no gap on the map.
2026-11-25: real road shapes + regional roads (step 03c): 1,663 of 1,792 lines traced (96% of
length), checked against the 2010 lines where an A/S road runs parallel (DK91 Gdańsk–Tczew,
DK8 Oleśnica, DK7 Elbląg, DK1 Piotrków–Częstochowa, DK2 Września, Katowice): the traces stay on
the old roads. Lines kept as on the map are mostly old routes that are now municipal roads
(not in BDOT national/regional, e.g. old DK8 east of Oleśnica) and very short town pieces.
The earlier BDOT-based 2010 attempts (`02_build_graph.py` past_network / pdf_network, steps
03/03b) are kept but give worse results.

## Outputs (`output/`)

| file | what |
|---|---|
| `traffic_network_2025.gpkg` | **main product** (EPSG:2180). It has QGIS default styles embedded, so drag it into QGIS |
| ├ `sections` | one line per GPR section: SDRR, vehicle classes, heavy share, status, QA |
| ├ `links`, `nodes` | modelling topology (sections split at junctions + uncounted connectors) |
| ├ `counting_points` | GPR counting stations |
| ├ `skdr_unmeasured` | operational national roads not covered by a section |
| ├ `regional_roads` | regional roads (drogi wojewódzkie) merged per road number |
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
