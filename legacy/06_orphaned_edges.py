"""
06_orphaned_edges.py
Find road edges with no SDRR/AADT assigned, sorted by length (longest first).

For each unmatched edge shows:
  - road_key, length, geometry centroid
  - up to 3 nearest GPR points (any road) with their road_key and distance

Helps identify whether the gap is a measurement-free section or a matching failure.

Reads:  output/roads_gpr2025.gpkg  (layer roads_gpr2025)
        output/gpr2025.csv
Writes: output/orphaned_edges.csv
"""

import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.strtree import STRtree

OUTPUT_DIR       = Path("output")
ROADS_GPKG       = OUTPUT_DIR / "roads_gpr2025.gpkg"
GPR_CSV          = OUTPUT_DIR / "gpr2025.csv"
OUT_CSV          = OUTPUT_DIR / "orphaned_edges.csv"

CANDIDATE_DIST_M = 50_000   # search radius for nearby GPR points
TOP_N            = 50       # how many longest unmatched edges to report

# ── Load edges ────────────────────────────────────────────────────────────────

print("Loading road edges …")
edges = gpd.read_file(ROADS_GPKG, layer="roads_gpr2025")
edges = edges[edges["join_method"] != "dummy"].copy()
edges["length_m"] = edges.geometry.length.round().astype(int)
edges["centroid"] = edges.geometry.centroid

unmatched = edges[edges["sdrr_total"].isna()].copy()
unmatched = unmatched.sort_values("length_m", ascending=False).reset_index(drop=True)

total     = len(edges)
n_unm     = len(unmatched)
print(f"  {total} total edges,  {n_unm} unmatched ({n_unm/total*100:.1f}%)")
print(f"  Unmatched length: {unmatched['length_m'].sum()/1000:.0f} km total, "
      f"longest = {unmatched['length_m'].iloc[0]/1000:.1f} km  (road {unmatched['road_key'].iloc[0]})")

# ── Load GPR points ───────────────────────────────────────────────────────────

print("\nLoading GPR points …")
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

gpr["road_key"] = gpr["nr_drogi"].apply(gpr_road_key)

gpr_gdf = gpd.GeoDataFrame(
    gpr,
    geometry=gpd.points_from_xy(gpr["pt_lon"], gpr["pt_lat"]),
    crs="EPSG:4326",
).to_crs("EPSG:2180")

gpr_pts   = list(gpr_gdf.geometry)
gpr_tree  = STRtree(gpr_pts)
print(f"  {len(gpr_gdf)} GPR points")

# ── For each unmatched edge find nearby GPR candidates ───────────────────────

print(f"\nAnalysing top {TOP_N} longest unmatched edges …")

rows = []
for _, row in unmatched.head(TOP_N).iterrows():
    centroid = row["centroid"]

    buf      = centroid.buffer(CANDIDATE_DIST_M)
    cand_idx = gpr_tree.query(buf, predicate="intersects")

    candidates = []
    for ci in cand_idx:
        dist = centroid.distance(gpr_pts[ci])
        candidates.append({
            "dist_m":   round(dist),
            "road_key": gpr_gdf.iloc[ci]["road_key"],
            "odcinek":  gpr_gdf.iloc[ci]["numer_odcinka"],
            "sdrr":     round(gpr_gdf.iloc[ci]["sdrr_total"]),
        })
    candidates.sort(key=lambda x: x["dist_m"])

    # Also list same-road GPR points separately
    same_road = [c for c in candidates if c["road_key"] == row["road_key"]]

    top = candidates[:3]
    rows.append({
        "road_key":       row["road_key"],
        "length_m":       row["length_m"],
        "seg_type":       row.get("seg_type", ""),
        "centroid_x":     round(centroid.x),
        "centroid_y":     round(centroid.y),
        "same_road_pts":  len(same_road),
        "nearest_same_dist_m": same_road[0]["dist_m"] if same_road else "",
        "cand1_road_key": top[0]["road_key"] if len(top) > 0 else "",
        "cand1_dist_m":   top[0]["dist_m"]   if len(top) > 0 else "",
        "cand1_sdrr":     top[0]["sdrr"]     if len(top) > 0 else "",
        "cand2_road_key": top[1]["road_key"] if len(top) > 1 else "",
        "cand2_dist_m":   top[1]["dist_m"]   if len(top) > 1 else "",
        "cand2_sdrr":     top[1]["sdrr"]     if len(top) > 1 else "",
        "cand3_road_key": top[2]["road_key"] if len(top) > 2 else "",
        "cand3_dist_m":   top[2]["dist_m"]   if len(top) > 2 else "",
        "cand3_sdrr":     top[2]["sdrr"]     if len(top) > 2 else "",
    })

df = pd.DataFrame(rows)

print(f"\n{'─'*90}")
print(df[["road_key", "length_m", "same_road_pts", "nearest_same_dist_m",
          "cand1_road_key", "cand1_dist_m"]].to_string(index=False))

df.to_csv(OUT_CSV, index=False)
print(f"\nSaved {OUT_CSV}")

# ── Summary by road ───────────────────────────────────────────────────────────

print(f"\nUnmatched km by road (top 15):")
by_road = (unmatched.groupby("road_key")["length_m"]
           .sum()
           .sort_values(ascending=False)
           .head(15))
for rk, km in by_road.items():
    print(f"  {rk:10s}  {km/1000:6.1f} km")
