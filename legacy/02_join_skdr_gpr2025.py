"""
join_skdr_gpr2025.py
Join GPR 2025 traffic data to SKDR national road geometry.

Reads:  output/gpr2025.csv        (from parse_gpr2025.py)
        D:/QGIS/BODT10k/SKDR/skdr_krajowe.gpkg

Writes: output/skdr_gpr2025.gpkg  (SKDR lines + sdrr_total column)
"""

import re
import pandas as pd
import geopandas as gpd
from pathlib import Path
from tqdm import tqdm

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SKDR_PATH = r"D:\QGIS\BODT10k\SKDR\skdr_krajowe.gpkg"
GPR_CSV   = OUTPUT_DIR / "gpr2025.csv"

# ---------------------------------------------------------------------------
# 1. Load GPR measurement points, reproject to CS92 (EPSG:2180)
# ---------------------------------------------------------------------------

print("Loading GPR data …")
gpr = pd.read_csv(GPR_CSV)
gpr = gpr.dropna(subset=["lat", "lon", "sdrr_total"]).copy()

gpr_gdf = gpd.GeoDataFrame(
    gpr,
    geometry=gpd.points_from_xy(gpr["lon"], gpr["lat"]),
    crs="EPSG:4326",
).to_crs("EPSG:2180")

print(f"  {len(gpr_gdf)} GPR sections with SDRR and coordinates")

# ---------------------------------------------------------------------------
# 2. Build a normalised road key for GPR
#    Rules: take first token before \n, extract prefix (A/S or empty) + number
#    e.g. 'A1' → 'A1',  'S7' → 'S7',  '61' → '61',  '10\n10a' → '10'
# ---------------------------------------------------------------------------

def gpr_road_key(val):
    if pd.isna(val):
        return None
    tok = str(val).split("\n")[0].strip()
    m = re.match(r"^([AS]?)(\d+)", tok)
    if m:
        return f"{m.group(1)}{int(m.group(2))}"
    return None

gpr_gdf["road_key"] = gpr_gdf["nr_drogi"].apply(gpr_road_key)

# ---------------------------------------------------------------------------
# 3. Load SKDR geometry
# ---------------------------------------------------------------------------

print("Loading SKDR geometry …")
skdr = gpd.read_file(SKDR_PATH, layer="skdr_krajowe")
skdr = skdr.to_crs("EPSG:2180")   # normalise CRS object (same projection, avoids mismatch warnings)
print(f"  {len(skdr)} features loaded, CRS: EPSG:2180")

# ---------------------------------------------------------------------------
# 4. Parse SKDR NUMER_DROG → road key, guided by KLASA_DROG
#
#    NUMER_DROG is pipe-separated and can contain:
#      plain integers   '94', '3'
#      pipe combos      '8|E67', '12|292', '297|94'
#      D-suffix codes   '103986D|94'  (internal segment IDs — skip)
#      class prefixes   'A4|E40', 'S3|E65'
#
#    Strategy: use KLASA_DROG to pick the right token.
# ---------------------------------------------------------------------------

def skdr_road_key(row):
    numer = row["NUMER_DROG"]
    klasa = row["KLASA_DROG"]
    if not numer:
        return None
    parts = [p.strip() for p in str(numer).split("|")]

    if klasa == "autostrada":
        for p in parts:
            if re.match(r"^A\d+$", p):
                return p
    elif klasa == "droga ekspresowa":
        for p in parts:
            if re.match(r"^S\d+$", p):
                return p
    else:  # droga główna ruchu przyśpieszonego / droga główna
        for p in parts:
            if re.match(r"^\d+$", p):
                return p
    return None

print("Parsing SKDR road keys …")
skdr["road_key"] = skdr.apply(skdr_road_key, axis=1)

n_null = skdr["road_key"].isna().sum()
print(f"  Road key parsed for {len(skdr) - n_null}/{len(skdr)} segments "
      f"({n_null} unparseable — will be unmatched)")

# ---------------------------------------------------------------------------
# 5. Spatial nearest-neighbour join, road by road
#
#    For each road key present in SKDR:
#      - Get all SKDR segment centroids for that road
#      - Get all GPR points for that road
#      - sjoin_nearest: each centroid → nearest GPR point (same road)
#      - Store (sdrr_total, gpr_odcinek, dist_m) back on the original SKDR index
#
#    Max distance: 15 km.  Beyond that the measurement likely belongs to a
#    different section / branch and we'd rather leave it unmatched.
# ---------------------------------------------------------------------------

MAX_DIST_M = 15_000

print("Joining by road (nearest-neighbour per road) …")

sdrr_map      = {}   # skdr_index → sdrr_total
odcinek_map   = {}   # skdr_index → numer_odcinka
dist_map      = {}   # skdr_index → dist_m

road_keys = skdr["road_key"].dropna().unique()

for road in tqdm(sorted(road_keys, key=str), desc="roads"):
    skdr_mask = skdr["road_key"] == road
    gpr_mask  = gpr_gdf["road_key"] == road

    skdr_idx = skdr.index[skdr_mask]
    gpr_sub  = gpr_gdf[gpr_mask]

    if gpr_sub.empty:
        continue  # leaves entries absent from maps → unmatched

    # Centroid GeoDataFrame for this road's SKDR segments
    centroids = gpd.GeoDataFrame(
        {"skdr_idx": skdr_idx},
        geometry=skdr.loc[skdr_idx, "geometry"].centroid.values,
        crs=skdr.crs,
    )

    joined = centroids.sjoin_nearest(
        gpr_sub[["geometry", "numer_odcinka", "sdrr_total"]].reset_index(drop=True),
        how="left",
        distance_col="dist_m",
        max_distance=MAX_DIST_M,
    )

    for _, row in joined.iterrows():
        i = row["skdr_idx"]
        sdrr_map[i]    = row.get("sdrr_total")
        odcinek_map[i] = row.get("numer_odcinka")
        dist_map[i]    = row.get("dist_m")

# ---------------------------------------------------------------------------
# 6. Apply mapping to SKDR, keeping original line geometry
# ---------------------------------------------------------------------------

print("Assembling output …")

skdr["sdrr_total"]   = skdr.index.map(sdrr_map)
skdr["gpr_odcinek"]  = skdr.index.map(odcinek_map)
skdr["dist_to_gpr_m"] = skdr.index.map(dist_map)

# join_method column for diagnostics
def join_method(row):
    if pd.isna(row["sdrr_total"]):
        return "unmatched"
    if row["dist_to_gpr_m"] < 500:
        return "nn_close"
    return "nn_far"

skdr["join_method"] = skdr.apply(join_method, axis=1)

# ---------------------------------------------------------------------------
# 7. Report match quality
# ---------------------------------------------------------------------------

total   = len(skdr)
matched = skdr["sdrr_total"].notna().sum()
close   = (skdr["join_method"] == "nn_close").sum()
far     = (skdr["join_method"] == "nn_far").sum()
unmatched = (skdr["join_method"] == "unmatched").sum()

print(f"\n--- Match report ---")
print(f"  Total SKDR segments  : {total:>7,}")
print(f"  Matched (any)        : {matched:>7,}  ({matched/total*100:.1f}%)")
print(f"    close  (<500 m)    : {close:>7,}")
print(f"    far    (>500 m)    : {far:>7,}")
print(f"  Unmatched            : {unmatched:>7,}  ({unmatched/total*100:.1f}%)")
print(f"\n  SDRR range (matched): "
      f"{skdr['sdrr_total'].min():.0f} – {skdr['sdrr_total'].max():.0f} poj./dobę")

# ---------------------------------------------------------------------------
# 8. Save
# ---------------------------------------------------------------------------

from shapely.geometry import LineString
dummy = skdr.iloc[[0]].copy()
dummy["sdrr_total"]    = 0
dummy["geometry"]      = LineString([(19.0, 52.0), (19.0001, 52.0)])  # ~8m stub
dummy["gpr_odcinek"]   = None
dummy["dist_to_gpr_m"] = None
dummy["join_method"]   = "dummy"
skdr = pd.concat([skdr, dummy], ignore_index=True)

out_path = OUTPUT_DIR / "skdr_gpr2025.gpkg"
skdr.to_file(out_path, layer="skdr_gpr2025", driver="GPKG")
print(f"\nSaved {out_path}")
print("Columns: NUMER_DROG, KLASA_DROG, road_key, sdrr_total, gpr_odcinek, "
      "dist_to_gpr_m, join_method, geometry")
print("\nLoad output/skdr_gpr2025.gpkg in QGIS, style by sdrr_total "
      "(graduated line width) to get the cartogram.")
