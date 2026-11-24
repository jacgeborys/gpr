"""
make_section_lines.py
Build straight-line section geometries from GPR 2025 measurement points.

Each section becomes a LineString from its measurement point to the next
section's measurement point along the same road (sorted by chainage).
This gives a connected linear network without needing SKDR geometry.

Reads:  output/gpr2025.csv
Writes: output/gpr2025_lines.gpkg  (EPSG:4326, one line per section)
"""

import re
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from pathlib import Path

OUTPUT_DIR = Path("output")

# ---------------------------------------------------------------------------
# 1. Load GPR data
# ---------------------------------------------------------------------------

df = pd.read_csv(OUTPUT_DIR / "gpr2025.csv")

for col in ["pik_pocz", "pik_konc", "dlugosc_km", "lat_prawy", "lon_prawy",
            "lat_lewy", "lon_lewy", "sdrr_total"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

print(f"Loaded {len(df)} sections")

# ---------------------------------------------------------------------------
# 2. Compute representative midpoint for each section
#    Use average of prawy + lewy coords. If only one side is available, use it.
# ---------------------------------------------------------------------------

def mid(a, b):
    """Mean of two values, or whichever is not NaN."""
    if pd.isna(a) and pd.isna(b):
        return float("nan")
    if pd.isna(a):
        return b
    if pd.isna(b):
        return a
    return (a + b) / 2

df["pt_lat"] = df.apply(lambda r: mid(r.lat_prawy, r.lat_lewy), axis=1)
df["pt_lon"] = df.apply(lambda r: mid(r.lon_prawy, r.lon_lewy), axis=1)

no_pt = df["pt_lat"].isna().sum()
print(f"  Sections with no coordinates: {no_pt} — will be skipped")
df = df.dropna(subset=["pt_lat", "pt_lon"]).copy()

# ---------------------------------------------------------------------------
# 3. Road key for the output attribute (display label only)
#    Grouping uses the full original nr_drogi — keeps '8', '8i', '8o' separate.
#    Sections with compound names ('8\n8o') are junction overlaps with no own
#    chainage — drop them as they can't be sequenced.
# ---------------------------------------------------------------------------

def display_road_key(val):
    """Simplified road key for the attribute table (A1, S7, 8, …)."""
    if pd.isna(val):
        return None
    tok = str(val).split("\n")[0].strip()
    m = re.match(r"^([AS]?)(\d+)", tok)
    return f"{m.group(1)}{int(m.group(2))}" if m else None

df["road_key"] = df["nr_drogi"].apply(display_road_key)

# Drop compound-name sections (contain \n) — they're junction overlaps
# and have no reliable chainage
compound_mask = df["nr_drogi"].astype(str).str.contains("\n", na=False)
n_compound = compound_mask.sum()
df = df[~compound_mask].copy()
print(f"  Dropped {n_compound} compound-name junction sections")

# Drop sections with no chainage (can't sequence them)
df = df.dropna(subset=["pik_pocz", "pik_konc"]).copy()
print(f"  {len(df)} sections remaining with chainage")

# ---------------------------------------------------------------------------
# 4. Build lines: group by exact nr_drogi (keeps 8, 8i, 8o separate),
#    sort by pik_pocz, connect consecutive points
# ---------------------------------------------------------------------------

lines = []

for road, grp in df.groupby("nr_drogi"):
    grp = grp.sort_values("pik_pocz").reset_index(drop=True)

    for i in range(len(grp) - 1):
        cur  = grp.iloc[i]
        nxt  = grp.iloc[i + 1]

        # Only connect if sections are plausibly adjacent (gap < 50 km in chainage)
        gap = nxt["pik_pocz"] - cur["pik_konc"]
        if gap > 50:
            continue

        geom = LineString([
            (cur["pt_lon"], cur["pt_lat"]),
            (nxt["pt_lon"], nxt["pt_lat"]),
        ])

        lines.append({
            "geometry":       geom,
            "road_key":       road,
            "nr_drogi":       cur["nr_drogi"],
            "numer_odcinka":  cur["numer_odcinka"],
            "nazwa_odcinka":  cur["nazwa_odcinka"],
            "pik_pocz":       cur["pik_pocz"],
            "pik_konc":       cur["pik_konc"],
            "dlugosc_km":     cur["dlugosc_km"],
            "sdrr_total":     cur["sdrr_total"],
            "sdrr_sam_osobowe":    cur["sdrr_sam_osobowe"],
            "sdrr_ciezarowe_bez":  cur["sdrr_ciezarowe_bez"],
            "sdrr_ciezarowe_z":    cur["sdrr_ciezarowe_z"],
            "sdrr_autobusy":       cur["sdrr_autobusy"],
        })

print(f"Built {len(lines)} section lines across {df['road_key'].nunique()} roads")

# ---------------------------------------------------------------------------
# 5. Save
# ---------------------------------------------------------------------------

gdf = gpd.GeoDataFrame(lines, crs="EPSG:4326")

out = OUTPUT_DIR / "gpr2025_lines.gpkg"
gdf.to_file(out, layer="gpr2025_lines", driver="GPKG")
print(f"Saved {out}")

# ---------------------------------------------------------------------------
# 6. Quick stats
# ---------------------------------------------------------------------------

matched = gdf["sdrr_total"].notna().sum()
print(f"\n  Lines with SDRR : {matched}/{len(gdf)}")
print(f"  SDRR range      : {gdf['sdrr_total'].min():.0f} – {gdf['sdrr_total'].max():.0f} poj./dobę")
print(f"  Roads covered   : {gdf['road_key'].nunique()}")
print(f"\nIn QGIS: load output/gpr2025_lines.gpkg, graduated line width by sdrr_total.")
