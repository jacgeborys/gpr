"""
05_orphaned_gpr.py
Find GPR measurement points that have no matching road edge within MAX_SDRR_DIST_M.

For each orphan, lists the 3 nearest road edges (any road_key) so we can
decide whether the mismatch is a road_key issue, a geometry gap, or a
measurement-only section not in SKDR.

Reads:  output/gpr2025.csv
        output/roads_gpr2025.gpkg  (layer roads_gpr2025)
Writes: output/orphaned_gpr.csv
"""

import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.strtree import STRtree

OUTPUT_DIR      = Path("output")
GPR_CSV         = OUTPUT_DIR / "gpr2025.csv"
ROADS_GPKG      = OUTPUT_DIR / "roads_gpr2025.gpkg"
OUT_CSV         = OUTPUT_DIR / "orphaned_gpr.csv"

MAX_SDRR_DIST_M = 20_000   # must match 03_build_graph.py
CANDIDATE_DIST_M = 30_000  # how far to search for nearby road candidates

# ── Load GPR points ───────────────────────────────────────────────────────────

print("Loading GPR points …")
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
gpr = gpr.dropna(subset=["road_key"])

gpr_gdf = gpd.GeoDataFrame(
    gpr,
    geometry=gpd.points_from_xy(gpr["pt_lon"], gpr["pt_lat"]),
    crs="EPSG:4326",
).to_crs("EPSG:2180")
print(f"  {len(gpr_gdf)} GPR points on {gpr_gdf['road_key'].nunique()} roads")

# ── Load road edges ───────────────────────────────────────────────────────────

print("Loading road edges …")
edges = gpd.read_file(ROADS_GPKG, layer="roads_gpr2025")
edges = edges[edges["join_method"] != "dummy"].copy()
edges["centroid"] = edges.geometry.centroid
print(f"  {len(edges)} edges on {edges['road_key'].nunique()} roads")

# ── For each GPR point: find nearest same-road edge ───────────────────────────

print("Checking each GPR point against same-road edges …")

# Build per-road centroid STRtree
road_centroids = {}
road_edge_index = {}
for rk, grp in edges.groupby("road_key"):
    road_centroids[rk] = list(grp["centroid"])
    road_edge_index[rk] = list(grp.index)

# Also build one global STRtree over all edge centroids for candidate lookup
all_centroids = list(edges["centroid"])
all_tree = STRtree(all_centroids)
all_edge_idx = list(edges.index)

rows = []

for _, pt_row in gpr_gdf.iterrows():
    pt     = pt_row.geometry
    rk     = pt_row["road_key"]
    fb     = numeric_fallback(rk)

    # Try exact road_key, then numeric fallback
    for key in ([rk, fb] if fb else [rk]):
        if key not in road_centroids:
            continue
        ctrs = road_centroids[key]
        dists = [pt.distance(c) for c in ctrs]
        min_dist = min(dists)
        if min_dist <= MAX_SDRR_DIST_M:
            break   # matched → skip this point
    else:
        # Not matched — find nearest road edges of ANY road_key as candidates
        buf = pt.buffer(CANDIDATE_DIST_M)
        cand_idxs = all_tree.query(buf, predicate="intersects")

        candidates = []
        for ci in cand_idxs:
            ei = all_edge_idx[ci]
            dist = pt.distance(all_centroids[ci])
            candidates.append({
                "dist_m":   round(dist),
                "road_key": edges.loc[ei, "road_key"],
                "edge_fid": ei,
            })
        candidates.sort(key=lambda x: x["dist_m"])
        top3 = candidates[:3]

        rows.append({
            "gpr_road_key":   rk,
            "nr_drogi":       pt_row.get("nr_drogi", ""),
            "numer_odcinka":  pt_row.get("numer_odcinka", ""),
            "sdrr_total":     pt_row.get("sdrr_total", ""),
            "pt_x":           round(pt.x),
            "pt_y":           round(pt.y),
            "reason":         "no_road_key" if rk not in road_centroids and (not fb or fb not in road_centroids) else "too_far",
            "cand1_road_key": top3[0]["road_key"] if len(top3) > 0 else "",
            "cand1_dist_m":   top3[0]["dist_m"]   if len(top3) > 0 else "",
            "cand2_road_key": top3[1]["road_key"] if len(top3) > 1 else "",
            "cand2_dist_m":   top3[1]["dist_m"]   if len(top3) > 1 else "",
            "cand3_road_key": top3[2]["road_key"] if len(top3) > 2 else "",
            "cand3_dist_m":   top3[2]["dist_m"]   if len(top3) > 2 else "",
        })

df = pd.DataFrame(rows)
print(f"\n{'─'*60}")
print(f"Orphaned GPR points: {len(df)}")

if len(df):
    print(f"\nBy reason:")
    print(df["reason"].value_counts().to_string())

    print(f"\nBy road_key (top 20):")
    print(df["gpr_road_key"].value_counts().head(20).to_string())

    print(f"\nSample rows:")
    print(df[["gpr_road_key", "numer_odcinka", "sdrr_total", "reason",
              "cand1_road_key", "cand1_dist_m"]].head(20).to_string(index=False))

    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {OUT_CSV}")
else:
    print("No orphaned GPR points — all are within MAX_SDRR_DIST_M of a matching edge.")
