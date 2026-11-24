"""
03_build_graph.py
Build a proper junction-to-junction graph of Polish national roads with GPR 2025 SDRR.

Segmentation strategy:
  A/S roads (motorways + expressways):
    → cut at named interchange points from skrw_wezly.gpkg
    → each edge = one interchange-to-interchange section
    → interchange name stored in węzeł_od / węzeł_do attributes

  National roads 1-99:
    → Pass 1: cut at krajowe×krajowe geometric intersections
    → Pass 2: if 2+ GPR sections span an edge, refine the cut by snapping
              to the nearest road crossing in priority order:
              1. wojewódzka  2. powiatowa  3. exact midpoint

SDRR assignment:
    → nearest GPR point on same road, capped at MAX_SDRR_DIST_M
    → for A/S roads: numeric fallback (A2 → try '2') if exact key missing
    → roads with no GPR point within cap shown as unmatched (no false assignment)

Reads:
  D:/QGIS/BODT10k/SKDR/skdr_krajowe.gpkg
  D:/QGIS/BODT10k/SKDR/skrw_wezly.gpkg
  D:/QGIS/BODT10k/SKDR/skdr_wojewodzkie.gpkg
  D:/QGIS/BODT10k/SKDR/skdr_powiatowe.gpkg
  output/gpr2025.csv

Writes:
  output/roads_gpr2025.gpkg   ← single output, layer 'roads_gpr2025'
"""

import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, substring
from shapely.strtree import STRtree
from tqdm import tqdm

OUTPUT_DIR    = Path("output")
SKDR_KRAJ     = r"D:\QGIS\BODT10k\SKDR\skdr_krajowe.gpkg"
SKDR_WEZLY    = r"D:\QGIS\BODT10k\SKDR\skrw_wezly.gpkg"
SKDR_WOJ      = r"D:\QGIS\BODT10k\SKDR\skdr_wojewodzkie.gpkg"
SKDR_POW      = r"D:\QGIS\BODT10k\SKDR\skdr_powiatowe.gpkg"
GPR_CSV       = OUTPUT_DIR / "gpr2025.csv"
OUTPUT_GPKG   = OUTPUT_DIR / "roads_gpr2025.gpkg"
OUTPUT_LAYER  = "roads_gpr2025"

SNAP_TOL_M        = 2.0    # road intersection point within 2m → on the line
INTERCHANGE_SNAP_M = 500.0 # interchange point within 500m → snaps to this A/S road
MIN_SEG_LEN_M     = 100.0  # discard segments shorter than this (geometry artefacts)
CARRIAGEWAY_M     = 60.0   # centroid gap between duplicate carriageway edges
GPR_PROJ_DIST_M   = 2000.0 # GPR point within 2km → eligible to project onto edge
POW_SEARCH_FRAC   = 0.15   # search window for lower-class road crossing: ±15% of edge
MAX_SDRR_DIST_M   = 20_000 # reject SDRR assignment if nearest GPR point > 20km away

# SKDR road_key → extra GPR road_keys to merge in (SKDR labelling lags GPR renumbering)
GPR_ROAD_ALIAS = {
    "19": ["9"],  # Rzeszów–Barwinek: SKDR still labels this corridor as 19, GPR uses 9
}

def collect_gpr(road, gpr_by_road):
    """Return merged GeoDataFrame of GPR points relevant to *road*.

    For A/S roads the numeric equivalent (A2→2, S7→7) is always merged in,
    not just used as a fallback.  Extra aliases from GPR_ROAD_ALIAS are also
    included.
    """
    parts = []
    sub = gpr_by_road.get(road)
    if sub is not None:
        parts.append(sub)
    fb = numeric_fallback(road)
    if fb:
        fb_sub = gpr_by_road.get(fb)
        if fb_sub is not None:
            parts.append(fb_sub)
    for alias in GPR_ROAD_ALIAS.get(road, []):
        a_sub = gpr_by_road.get(alias)
        if a_sub is not None:
            parts.append(a_sub)
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]

# ── 1. Load & parse road_key ──────────────────────────────────────────────────

print("Loading SKDR krajowe …")
kraj = gpd.read_file(SKDR_KRAJ, layer="skdr_krajowe").to_crs("EPSG:2180")
print(f"  {len(kraj):,} micro-segments")

def skdr_road_key(row):
    numer, klasa = row["NUMER_DROG"], row["KLASA_DROG"]
    if not numer:
        return None
    parts = [p.strip() for p in re.split(r"[|;]", str(numer))]
    if klasa == "autostrada":
        for p in parts:
            if re.match(r"^A\d+$", p): return p
    elif klasa == "droga ekspresowa":
        for p in parts:
            if re.match(r"^S\d+$", p): return p
    else:
        for p in parts:
            if re.match(r"^\d+$", p): return p
    for p in parts:
        if re.match(r"^\d+$", p): return p
    for p in parts:
        if re.match(r"^[AS]\d+$", p): return p
    return None

kraj["road_key"] = kraj.apply(skdr_road_key, axis=1)
kraj_k = kraj.dropna(subset=["road_key"]).copy()
print(f"  {len(kraj_k):,} with road_key  ({kraj['road_key'].isna().sum()} skipped)")

def is_as(rk):
    return bool(re.match(r"^[AS]\d+$", str(rk)))

# ── 2. Load support layers ────────────────────────────────────────────────────

print("Loading interchange points (skrw_wezly) …")
wezly = gpd.read_file(SKDR_WEZLY).to_crs("EPSG:2180")
wezly_op = wezly[
    (wezly["KAT_ISTNIE"] == "eksploatowany") &
    wezly["NAZWA_WEZL"].notna()
].copy()
wezly_geoms = list(wezly_op.geometry)
wezly_names = list(wezly_op["NAZWA_WEZL"].fillna(""))
wezly_tree  = STRtree(wezly_geoms)
print(f"  {len(wezly_op)} operational interchanges")

print("Loading SKDR wojewódzkie …")
woj_gdf  = gpd.read_file(SKDR_WOJ).to_crs("EPSG:2180")
woj_geoms = list(woj_gdf.geometry)
woj_tree  = STRtree(woj_geoms)
print(f"  {len(woj_gdf):,} segments")

print("Loading SKDR powiatowe …")
pow_gdf  = gpd.read_file(SKDR_POW).to_crs("EPSG:2180")
pow_geoms = list(pow_gdf.geometry)
pow_tree  = STRtree(pow_geoms)
print(f"  {len(pow_gdf):,} segments")

# ── 3. Merge micro-segments into full road geometries ─────────────────────────

print("Merging micro-segments per road_key …")
road_geoms = {}
for road_key_val, grp in tqdm(kraj_k.groupby("road_key"),
                               total=kraj_k["road_key"].nunique(), desc="roads"):
    road_geoms[road_key_val] = linemerge(list(grp.geometry))
print(f"  {len(road_geoms)} road geometries")

# ── 4. Load GPR measurement points ───────────────────────────────────────────

print("\nLoading GPR data …")
gpr = pd.read_csv(GPR_CSV)
for col in ["lat_prawy", "lat_lewy", "lon_prawy", "lon_lewy", "sdrr_total"]:
    gpr[col] = pd.to_numeric(gpr[col], errors="coerce")
gpr["pt_lat"] = gpr[["lat_prawy", "lat_lewy"]].mean(axis=1)
gpr["pt_lon"] = gpr[["lon_prawy", "lon_lewy"]].mean(axis=1)
gpr = gpr.dropna(subset=["pt_lat", "pt_lon", "sdrr_total"])

def gpr_road_key(val):
    if pd.isna(val): return None
    tok = str(val).split("\n")[0].strip()
    m = re.match(r"^([AS]?)(\d+)", tok)
    return f"{m.group(1)}{int(m.group(2))}" if m else None

def numeric_fallback(rk):
    m = re.match(r"^([AS])(\d+)$", str(rk))
    return m.group(2) if m else None

gpr["road_key"] = gpr["nr_drogi"].apply(gpr_road_key)

gpr_gdf = gpd.GeoDataFrame(
    gpr,
    geometry=gpd.points_from_xy(gpr["pt_lon"], gpr["pt_lat"]),
    crs="EPSG:4326",
).to_crs("EPSG:2180")

gpr_by_road = {rk: grp.copy() for rk, grp in gpr_gdf.groupby("road_key")}
print(f"  {len(gpr_gdf)} GPR points across {len(gpr_by_road)} roads")

# ── helpers ───────────────────────────────────────────────────────────────────

def extract_pts(geom):
    t = geom.geom_type
    if t == "Point":         return [geom]
    if t == "MultiPoint":    return list(geom.geoms)
    if t in ("LineString", "LinearRing"):
        return [Point(geom.coords[0]), Point(geom.coords[-1])]
    if t == "MultiLineString":
        pts = []
        for ln in geom.geoms: pts += [Point(ln.coords[0]), Point(ln.coords[-1])]
        return pts
    if t == "GeometryCollection":
        pts = []
        for g in geom.geoms: pts += extract_pts(g)
        return pts
    return []

def cut_line_at_fracs(line, fracs, min_len=MIN_SEG_LEN_M):
    all_fracs = sorted({0.0, 1.0} | set(fracs))
    segs = []
    for i in range(len(all_fracs) - 1):
        seg = substring(line, all_fracs[i], all_fracs[i+1], normalized=True)
        if seg is not None and not seg.is_empty and seg.length >= min_len:
            segs.append(seg)
    return segs

def find_nearest_crossing(geom, boundary_frac, tree, geom_list):
    boundary_pt = geom.interpolate(boundary_frac, normalized=True)
    frac_window = geom.length * POW_SEARCH_FRAC
    search_buf  = boundary_pt.buffer(frac_window)
    candidates  = tree.query(search_buf, predicate="intersects")
    best_frac, best_delta = None, float("inf")
    for idx in candidates:
        inter = geom.intersection(geom_list[idx])
        if inter.is_empty: continue
        for ipt in extract_pts(inter):
            if geom.distance(ipt) > SNAP_TOL_M: continue
            f = geom.project(ipt, normalized=True)
            if not (0.0 < f < 1.0): continue
            delta = abs(f - boundary_frac)
            if delta < best_delta:
                best_delta, best_frac = delta, f
    return best_frac

# ── 5. Pass 1a: A/S roads → cut at interchange points ────────────────────────

print("\n=== Pass 1a: A/S roads → interchange-based segmentation ===")

primary_edges = []
as_roads = [rk for rk in road_geoms if is_as(rk)]

for road_key_val in tqdm(sorted(as_roads), desc="A/S roads"):
    road_geom = road_geoms[road_key_val]
    parts = ([road_geom] if road_geom.geom_type == "LineString"
             else list(road_geom.geoms))

    for part in parts:
        if part.length < MIN_SEG_LEN_M: continue

        # Find operational interchanges near this road part
        cands = wezly_tree.query(part.buffer(INTERCHANGE_SNAP_M), predicate="intersects")
        cut_fracs = {}  # frac → interchange name
        for idx in cands:
            pt = wezly_geoms[idx]
            if part.distance(pt) <= INTERCHANGE_SNAP_M:
                frac = part.project(pt, normalized=True)
                if 0.0 < frac < 1.0:
                    cut_fracs[frac] = wezly_names[idx]

        all_fracs = sorted({0.0, 1.0} | set(cut_fracs))
        for i in range(len(all_fracs) - 1):
            seg = substring(part, all_fracs[i], all_fracs[i+1], normalized=True)
            if seg is None or seg.is_empty or seg.length < MIN_SEG_LEN_M:
                continue
            primary_edges.append({
                "road_key":   road_key_val,
                "seg_type":   "interchange",
                "wezly_od":   cut_fracs.get(all_fracs[i],   ""),
                "wezly_do":   cut_fracs.get(all_fracs[i+1], ""),
                "geometry":   seg,
            })

n_as = len(primary_edges)
print(f"  {n_as} A/S edges from interchange segmentation")

# ── 6. Pass 1b: national roads → road-road intersections ─────────────────────

print("\n=== Pass 1b: national roads → krajowe×krajowe intersections ===")

nat_roads = [rk for rk in road_geoms if not is_as(rk)]
road_list  = [(rk, road_geoms[rk]) for rk in nat_roads]
n_pairs    = len(road_list) * (len(road_list) - 1) // 2

split_pts_kk = defaultdict(list)
for (rk1, g1), (rk2, g2) in tqdm(combinations(road_list, 2),
                                   total=n_pairs, desc="pairs"):
    b1, b2 = g1.bounds, g2.bounds
    if b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1]: continue
    inter = g1.intersection(g2)
    if inter.is_empty: continue
    pts = extract_pts(inter)
    split_pts_kk[rk1].extend(pts)
    split_pts_kk[rk2].extend(pts)

print(f"  {sum(len(v) for v in split_pts_kk.values()):,} split points")

for road_key_val in tqdm(nat_roads, desc="national roads"):
    road_geom = road_geoms[road_key_val]
    pts   = split_pts_kk.get(road_key_val, [])
    parts = ([road_geom] if road_geom.geom_type == "LineString"
             else list(road_geom.geoms))

    for part in parts:
        if part.length < MIN_SEG_LEN_M: continue
        local_pts = [p for p in pts if part.distance(p) <= SNAP_TOL_M]
        fracs = {part.project(p, normalized=True) for p in local_pts}
        for seg in cut_line_at_fracs(part, fracs):
            primary_edges.append({
                "road_key": road_key_val,
                "seg_type": "intersection",
                "wezly_od": "",
                "wezly_do": "",
                "geometry": seg,
            })

primary_gdf = gpd.GeoDataFrame(primary_edges, crs="EPSG:2180")
print(f"\n  Total primary edges: {len(primary_gdf):,}  "
      f"(A/S: {n_as}, national: {len(primary_gdf)-n_as})")

# ── 7. Pass 2: refine national road edges at GPR section boundaries ───────────
#  Only for national roads — A/S roads already have the correct nodes.

print("\n=== Pass 2: refine national road edges at GPR boundaries ===")

refined_edges = []
stats = {"refined": 0, "woj": 0, "pow": 0, "midpoint": 0}

for _, row in tqdm(primary_gdf.iterrows(), total=len(primary_gdf), desc="edges"):
    rk   = row["road_key"]
    geom = row["geometry"]

    # A/S roads: keep as-is
    if is_as(rk):
        refined_edges.append(row.to_dict())
        continue

    # GPR points for this national road
    gpr_sub = collect_gpr(rk, gpr_by_road)

    if gpr_sub is None:
        refined_edges.append(row.to_dict())
        continue

    # Project GPR points onto this edge
    on_edge = []
    for _, gpr_row in gpr_sub.iterrows():
        pt = gpr_row.geometry
        if geom.distance(pt) > GPR_PROJ_DIST_M: continue
        frac = geom.project(pt, normalized=True)
        if 0.0 < frac < 1.0:
            on_edge.append({"frac": frac, "numer_odcinka": gpr_row["numer_odcinka"]})

    if len({e["numer_odcinka"] for e in on_edge}) <= 1:
        refined_edges.append(row.to_dict())
        continue

    on_edge.sort(key=lambda e: e["frac"])
    cut_fracs = set()
    stats["refined"] += 1

    for k in range(len(on_edge) - 1):
        if on_edge[k]["numer_odcinka"] == on_edge[k+1]["numer_odcinka"]: continue
        boundary_frac = (on_edge[k]["frac"] + on_edge[k+1]["frac"]) / 2.0

        f = find_nearest_crossing(geom, boundary_frac, woj_tree, woj_geoms)
        if f is not None:
            cut_fracs.add(f); stats["woj"] += 1; continue
        f = find_nearest_crossing(geom, boundary_frac, pow_tree, pow_geoms)
        if f is not None:
            cut_fracs.add(f); stats["pow"] += 1; continue
        cut_fracs.add(boundary_frac); stats["midpoint"] += 1

    if not cut_fracs:
        refined_edges.append(row.to_dict())
        continue

    base = row.to_dict()
    for seg in cut_line_at_fracs(geom, cut_fracs):
        e = dict(base)
        e["geometry"] = seg
        e["wezly_od"] = ""
        e["wezly_do"] = ""
        refined_edges.append(e)

edges = gpd.GeoDataFrame(refined_edges, crs="EPSG:2180")
print(f"  {stats['refined']} national edges refined  "
      f"(woj: {stats['woj']}, pow: {stats['pow']}, midpoint: {stats['midpoint']})")
print(f"  {len(primary_gdf):,} primary → {len(edges):,} refined edges")

# ── 8. Deduplicate parallel carriageway edges ─────────────────────────────────

print("\nDeduplicating parallel carriageway edges …")
to_drop = set()

for rk, grp in tqdm(edges.groupby("road_key"), desc="roads"):
    idxs     = list(grp.index)
    if len(idxs) <= 1: continue
    centroids = [edges.loc[i, "geometry"].centroid for i in idxs]
    lengths   = [edges.loc[i, "geometry"].length   for i in idxs]

    for i in range(len(idxs)):
        if idxs[i] in to_drop: continue
        for j in range(i + 1, len(idxs)):
            if idxs[j] in to_drop: continue
            if centroids[i].distance(centroids[j]) > CARRIAGEWAY_M: continue
            li, lj = lengths[i], lengths[j]
            if li == 0 or lj == 0: continue
            if min(li, lj) / max(li, lj) < 0.5: continue
            if li >= lj: to_drop.add(idxs[j])
            else:        to_drop.add(idxs[i]); break

edges = edges[~edges.index.isin(to_drop)].reset_index(drop=True)
lengths_post = edges.geometry.length
print(f"  Removed {len(to_drop)} duplicate carriageway edges")
print(f"  {len(edges):,} edges  |  median {lengths_post.median():,.0f}m  "
      f"|  <500m: {(lengths_post < 500).sum()}  |  >10km: {(lengths_post > 10_000).sum()}")

# ── 9. Assign SDRR ────────────────────────────────────────────────────────────

print("\nAssigning SDRR …")
sdrr_map = {}; odcinek_map = {}; dist_map = {}

for road in tqdm(sorted(edges["road_key"].dropna().unique(), key=str), desc="roads"):
    edge_idx = edges.index[edges["road_key"] == road]
    gpr_sub = collect_gpr(road, gpr_by_road)
    if gpr_sub is None: continue

    edge_geoms_sub = gpd.GeoDataFrame(
        {"edge_idx": edge_idx},
        geometry=edges.loc[edge_idx, "geometry"].values,
        crs="EPSG:2180",
    )
    joined = edge_geoms_sub.sjoin_nearest(
        gpr_sub[["geometry", "numer_odcinka", "sdrr_total"]].reset_index(drop=True),
        how="left", distance_col="dist_m", max_distance=MAX_SDRR_DIST_M,
    )
    for _, row in joined.iterrows():
        i = row["edge_idx"]
        sdrr_map[i]    = row.get("sdrr_total")
        odcinek_map[i] = row.get("numer_odcinka")
        dist_map[i]    = row.get("dist_m")

edges["sdrr_total"]    = edges.index.map(sdrr_map)
edges["gpr_odcinek"]   = edges.index.map(odcinek_map)
edges["dist_to_gpr_m"] = edges.index.map(dist_map)

# ── 9b. Cross-road fallback for superseded / unmatched edges ─────────────────
#  For each still-unmatched edge, snap to the nearest matched edge that has SDRR,
#  trying expressways (S*) first, then motorways (A*), then any road.

print("\nCross-road fallback for remaining unmatched edges …")
CROSS_ROAD_DIST_M = 10_000
cross_road_idx = set()

unmatched_mask = edges["sdrr_total"].isna()
n_before = int(unmatched_mask.sum())

if n_before > 0:
    matched_pool = edges[edges["sdrr_total"].notna()].copy()
    remaining    = set(edges.index[unmatched_mask].tolist())

    for label, filt in [
        ("S-roads", lambda rk: str(rk).startswith("S")),
        ("A-roads", lambda rk: str(rk).startswith("A")),
        ("any",     lambda rk: True),
    ]:
        if not remaining:
            break
        candidates = matched_pool[matched_pool["road_key"].apply(filt)].reset_index(drop=True)
        if candidates.empty:
            continue
        rem_list  = sorted(remaining)
        rem_geoms = gpd.GeoDataFrame(
            {"orig_idx": rem_list},
            geometry=edges.loc[rem_list, "geometry"].values,
            crs="EPSG:2180",
        )
        joined = rem_geoms.sjoin_nearest(
            candidates[["geometry", "sdrr_total", "gpr_odcinek"]],
            how="left", distance_col="dist_m", max_distance=CROSS_ROAD_DIST_M,
        )
        for _, row in joined.iterrows():
            if pd.isna(row.get("sdrr_total")):
                continue
            i = int(row["orig_idx"])
            if i not in remaining:
                continue
            edges.at[i, "sdrr_total"]    = row["sdrr_total"]
            edges.at[i, "gpr_odcinek"]   = row.get("gpr_odcinek")
            edges.at[i, "dist_to_gpr_m"] = row["dist_m"]
            cross_road_idx.add(i)
            remaining.discard(i)

    print(f"  Matched {n_before - len(remaining)} of {n_before} edges via cross-road fallback"
          f"  ({len(remaining)} still unmatched)")

def join_method(row):
    if pd.isna(row["sdrr_total"]):    return "unmatched"
    if row.name in cross_road_idx:    return "cross_road"
    if row["dist_to_gpr_m"] <   500:  return "nn_close"
    if row["dist_to_gpr_m"] < 5_000:  return "nn_near"
    return "nn_far"

edges["join_method"] = edges.apply(join_method, axis=1)

# Dummy row for QGIS graduated symbology
dummy = edges.iloc[[0]].copy()
dummy["sdrr_total"]    = 0
dummy["geometry"]      = LineString([(500000, 200000), (500001, 200000)])
dummy["gpr_odcinek"]   = None
dummy["dist_to_gpr_m"] = None
dummy["join_method"]   = "dummy"
dummy["wezly_od"]      = ""
dummy["wezly_do"]      = ""
edges = pd.concat([edges, dummy], ignore_index=True)

# ── 10. Report & save ─────────────────────────────────────────────────────────

total     = len(edges) - 1
matched   = edges.iloc[:-1]["sdrr_total"].notna().sum()
unmatched = total - matched

print(f"\n--- Match report ---")
print(f"  Total edges  : {total:>8,}")
print(f"  Matched      : {matched:>8,}  ({matched/total*100:.1f}%)")
print(f"  Unmatched    : {unmatched:>8,}  ({unmatched/total*100:.1f}%)")
if unmatched > 0:
    unk = edges.iloc[:-1][edges.iloc[:-1]["sdrr_total"].isna()]
    for rk, cnt in unk["road_key"].value_counts().head(15).items():
        print(f"    {rk:10s}  {cnt}")

edges.to_file(OUTPUT_GPKG, layer=OUTPUT_LAYER, driver="GPKG")
print(f"\nSaved {OUTPUT_GPKG}  (layer: {OUTPUT_LAYER})")
