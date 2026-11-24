"""
build_network.py
Split national road (SKDR krajowe) segments at every intersection with
regional roads (wojewódzkie), then re-assign GPR 2025 SDRR to each
resulting sub-segment.

Reads:
  D:/QGIS/BODT10k/SKDR/skdr_krajowe.gpkg
  D:/QGIS/BODT10k/SKDR/skdr_wojewodzkie.gpkg
  output/gpr2025.csv

Writes:
  output/skdr_split.gpkg          — national roads split at DW intersections
  output/skdr_split_gpr2025.gpkg  — split segments with SDRR assigned
"""

import re
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.ops import substring
from pathlib import Path
from tqdm import tqdm

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SKDR_KRAJ = r"D:\QGIS\BODT10k\SKDR\skdr_krajowe.gpkg"
SKDR_WOJ  = r"D:\QGIS\BODT10k\SKDR\skdr_wojewodzkie.gpkg"
GPR_CSV   = OUTPUT_DIR / "gpr2025.csv"
SNAP_TOL  = 0.5   # metres — minimum sub-segment length to keep

# ---------------------------------------------------------------------------
# 1. Load road layers, normalise CRS
# ---------------------------------------------------------------------------

print("Loading road layers …")
kraj = gpd.read_file(SKDR_KRAJ, layer="skdr_krajowe").to_crs("EPSG:2180")
woj  = gpd.read_file(SKDR_WOJ,  layer="skdr_wojewodzkie").to_crs("EPSG:2180")
print(f"  krajowe:     {len(kraj):>7,} segments")
print(f"  wojewódzkie: {len(woj):>7,} segments")

# ---------------------------------------------------------------------------
# 2. Parse national road key (reuse logic from join script)
# ---------------------------------------------------------------------------

def skdr_road_key(row):
    numer = row["NUMER_DROG"]
    klasa = row["KLASA_DROG"]
    if not numer:
        return None
    parts = [p.strip() for p in str(numer).split("|")]
    if klasa == "autostrada":
        for p in parts:
            if re.match(r"^A\d+$", p): return p
    elif klasa == "droga ekspresowa":
        for p in parts:
            if re.match(r"^S\d+$", p): return p
    else:
        for p in parts:
            if re.match(r"^\d+$", p): return p
    return None

kraj["road_key"] = kraj.apply(skdr_road_key, axis=1)

# ---------------------------------------------------------------------------
# 3. Build spatial index on wojewódzkie, find intersections, split
# ---------------------------------------------------------------------------

def split_line_at_points(line, split_points):
    """Split a LineString at a list of Points; return list of sub-LineStrings."""
    dists = sorted({
        round(line.project(p), 4)
        for p in split_points
        if SNAP_TOL < line.project(p) < line.length - SNAP_TOL
    })
    if not dists:
        return [line]
    result = []
    prev = 0.0
    for d in dists:
        if d - prev < SNAP_TOL:
            continue
        seg = substring(line, prev, d)
        if seg and not seg.is_empty and seg.length >= SNAP_TOL:
            result.append(seg)
        prev = d
    tail = substring(line, prev, line.length)
    if tail and not tail.is_empty and tail.length >= SNAP_TOL:
        result.append(tail)
    return result if result else [line]

print("Building spatial index on wojewódzkie …")
woj_sindex = woj.sindex

print("Splitting krajowe at DW intersections …")
rows = []
for idx, seg in tqdm(kraj.iterrows(), total=len(kraj), desc="segments"):
    geom = seg.geometry
    if geom is None or geom.is_empty:
        continue

    # Candidate DW segments whose bounding box overlaps
    candidates = list(woj_sindex.intersection(geom.bounds))
    split_pts = []
    for c in candidates:
        woj_geom = woj.geometry.iloc[c]
        if geom.intersects(woj_geom):
            pt = geom.intersection(woj_geom)
            # intersection may be Point, MultiPoint, or GeometryCollection
            if pt.geom_type == "Point":
                split_pts.append(pt)
            elif pt.geom_type == "MultiPoint":
                split_pts.extend(pt.geoms)
            elif pt.geom_type == "GeometryCollection":
                for g in pt.geoms:
                    if g.geom_type == "Point":
                        split_pts.append(g)

    sub_lines = split_line_at_points(geom, split_pts)

    for sub in sub_lines:
        rows.append({
            "geometry":    sub,
            "KAT_ZARZAD":  seg["KAT_ZARZAD"],
            "KLASA_DROG":  seg["KLASA_DROG"],
            "NUMER_DROG":  seg["NUMER_DROG"],
            "LICZ_JEZDN":  seg["LICZ_JEZDN"],
            "SZER_NAWIE":  seg["SZER_NAWIE"],
            "road_key":    seg["road_key"],
            "orig_idx":    idx,
        })

split_gdf = gpd.GeoDataFrame(rows, crs="EPSG:2180")
print(f"\nSplit result: {len(kraj)} → {len(split_gdf)} segments "
      f"(avg {len(split_gdf)/len(kraj):.1f}x)")

split_gdf.to_file(OUTPUT_DIR / "skdr_split.gpkg", layer="skdr_split", driver="GPKG")
print(f"Saved output/skdr_split.gpkg")

# ---------------------------------------------------------------------------
# 4. Assign GPR 2025 SDRR to split segments (nearest-neighbour per road)
# ---------------------------------------------------------------------------

print("\nLoading GPR data …")
gpr = pd.read_csv(GPR_CSV)
for col in ["lat_prawy","lat_lewy","lon_prawy","lon_lewy","sdrr_total"]:
    gpr[col] = pd.to_numeric(gpr[col], errors="coerce")
gpr["pt_lat"] = gpr[["lat_prawy","lat_lewy"]].mean(axis=1)
gpr["pt_lon"] = gpr[["lon_prawy","lon_lewy"]].mean(axis=1)
gpr = gpr.dropna(subset=["pt_lat","pt_lon","sdrr_total"])

def gpr_road_key(val):
    if pd.isna(val): return None
    tok = str(val).split("\n")[0].strip()
    m = re.match(r"^([AS]?)(\d+)", tok)
    return f"{m.group(1)}{int(m.group(2))}" if m else None

gpr["road_key"] = gpr["nr_drogi"].apply(gpr_road_key)

gpr_gdf = gpd.GeoDataFrame(
    gpr, geometry=gpd.points_from_xy(gpr["pt_lon"], gpr["pt_lat"]), crs="EPSG:4326"
).to_crs("EPSG:2180")

print("Joining SDRR to split segments …")
MAX_DIST_M = 15_000
sdrr_map    = {}
odcinek_map = {}
dist_map    = {}

road_keys = split_gdf["road_key"].dropna().unique()

for road in tqdm(sorted(road_keys, key=str), desc="roads"):
    seg_mask = split_gdf["road_key"] == road
    gpr_mask = gpr_gdf["road_key"] == road

    seg_idx = split_gdf.index[seg_mask]
    gpr_sub = gpr_gdf[gpr_mask]
    if gpr_sub.empty:
        continue

    centroids = gpd.GeoDataFrame(
        {"seg_idx": seg_idx},
        geometry=split_gdf.loc[seg_idx, "geometry"].centroid.values,
        crs="EPSG:2180",
    )
    joined = centroids.sjoin_nearest(
        gpr_sub[["geometry","numer_odcinka","sdrr_total"]].reset_index(drop=True),
        how="left", distance_col="dist_m", max_distance=MAX_DIST_M,
    )
    for _, row in joined.iterrows():
        i = row["seg_idx"]
        sdrr_map[i]    = row.get("sdrr_total")
        odcinek_map[i] = row.get("numer_odcinka")
        dist_map[i]    = row.get("dist_m")

split_gdf["sdrr_total"]    = split_gdf.index.map(sdrr_map)
split_gdf["gpr_odcinek"]   = split_gdf.index.map(odcinek_map)
split_gdf["dist_to_gpr_m"] = split_gdf.index.map(dist_map)

def join_method(row):
    if pd.isna(row["sdrr_total"]):   return "unmatched"
    if row["dist_to_gpr_m"] < 500:  return "nn_close"
    return "nn_far"

split_gdf["join_method"] = split_gdf.apply(join_method, axis=1)

# Dummy row so QGIS graduated symbology anchors at 0
from shapely.geometry import LineString as LS
dummy = split_gdf.iloc[[0]].copy()
dummy["sdrr_total"]    = 0
dummy["geometry"]      = LS([(500000, 200000), (500001, 200000)])
dummy["gpr_odcinek"]   = None
dummy["dist_to_gpr_m"] = None
dummy["join_method"]   = "dummy"
split_gdf = pd.concat([split_gdf, dummy], ignore_index=True)

# ---------------------------------------------------------------------------
# 5. Report & save
# ---------------------------------------------------------------------------

total     = len(split_gdf) - 1  # exclude dummy
matched   = split_gdf.iloc[:-1]["sdrr_total"].notna().sum()
unmatched = total - matched

print(f"\n--- Match report ---")
print(f"  Total split segments : {total:>8,}")
print(f"  Matched              : {matched:>8,}  ({matched/total*100:.1f}%)")
print(f"  Unmatched            : {unmatched:>8,}  ({unmatched/total*100:.1f}%)")

out = OUTPUT_DIR / "skdr_split_gpr2025.gpkg"
split_gdf.to_file(out, layer="skdr_split_gpr2025", driver="GPKG")
print(f"\nSaved {out}")
