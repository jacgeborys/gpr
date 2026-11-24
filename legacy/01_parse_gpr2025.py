"""
parse_gpr2025.py
Parse GPR 2025 Excel files (Tab01 + Tab02), join them, and export:
  - output/gpr2025.csv   — flat CSV for inspection / QGIS joins
  - output/gpr2025.gpkg  — GeoPackage with measurement points (WGS84, EPSG:4326)
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Read raw Excel files
# ---------------------------------------------------------------------------

TAB01 = "Tab01_25_dk_KRAJ_20260414.xlsx"
TAB02 = "Tab02_25_dk_KRAJ_20260414.xlsx"

COL_NAMES_TAB01 = [
    "numer_odcinka",        # 0  — join key
    "nr_drogi",             # 1  — road number (A1, 1, 61 …)
    "nr_europejski",        # 2  — E-road designation
    "pik_pocz",             # 3  — chainage start (km)
    "pik_konc",             # 4  — chainage end (km)
    "dlugosc_km",           # 5  — section length (km)
    "nazwa_odcinka",        # 6  — section name
    "typ_odcinka",          # 7  — section type
    "pik_prawy",            # 8  — right-point chainage
    "pik_lewy",             # 9  — left-point chainage
    "miejscowosc",          # 10 — locality
    "lat_prawy",            # 11 — WGS84 latitude  (right point)
    "lon_prawy",            # 12 — WGS84 longitude (right point)
    "y_cs92_prawy",         # 13 — CS92 Y (right)
    "x_cs92_prawy",         # 14 — CS92 X (right)
    "lat_lewy",             # 15 — WGS84 latitude  (left point)
    "lon_lewy",             # 16 — WGS84 longitude (left point)
    "y_cs92_lewy",          # 17 — CS92 Y (left)
    "x_cs92_lewy",          # 18 — CS92 X (left)
    "nazwa_rejonu",         # 19 — GDDKiA district name
    "nr_rejonu",            # 20 — GDDKiA district number
    "pomiar_rozszerzony",   # 21
    "pomiar_jezdnie_dod",   # 22
    "pomiar_jezdnie_zakres",# 23
    "pomiar_uzupelniajacy", # 24
    "nr_stacji_scpr",       # 25
    "siec_tent",            # 26
    "odcinki_sasiednie",    # 27
    "odcinek_gpr2020",      # 28 — corresponding 2020/21 section number
    "uwagi",                # 29
    "nr_woj",               # 30 — voivodeship number
    "nr_kolejny",           # 31
]

COL_NAMES_TAB02 = [
    "numer_odcinka",        # 0  — join key
    "nr_drogi",             # 1
    "nr_europejski",        # 2
    "pik_pocz",             # 3
    "pik_konc",             # 4
    "dlugosc_km",           # 5
    "nazwa_odcinka",        # 6
    "typ_odcinka",          # 7
    "sdrr_total",           # 8  — SDRR total (vehicles/day) *** main value ***
    "sdrr_motocykle",       # 9
    "sdrr_sam_osobowe",     # 10
    "sdrr_mikrobusy",       # 11
    "sdrr_lekkie_ciezarowe",# 12
    "sdrr_ciezarowe_bez",   # 13 — trucks without trailer
    "sdrr_ciezarowe_z",     # 14 — trucks with trailer
    "sdrr_autobusy",        # 15
    "sdrr_ciagniki",        # 16
    "nr_woj",               # 17
    "kolejnosc",            # 18
    "uwagi",                # 19
]

print("Reading Tab01 …")
tab01 = pd.read_excel(TAB01, header=None, skiprows=11, names=COL_NAMES_TAB01, engine="openpyxl")

print("Reading Tab02 …")
tab02 = pd.read_excel(TAB02, header=None, skiprows=10, names=COL_NAMES_TAB02, engine="openpyxl")

print(f"  Tab01: {len(tab01)} rows | Tab02: {len(tab02)} rows")

# ---------------------------------------------------------------------------
# 2. Clean up & align join key types
# ---------------------------------------------------------------------------

tab01["numer_odcinka"] = pd.to_numeric(tab01["numer_odcinka"], errors="coerce").astype("Int64")
tab02["numer_odcinka"] = pd.to_numeric(tab02["numer_odcinka"], errors="coerce").astype("Int64")

# Drop the duplicate columns from tab02 that are already in tab01
tab02_traffic_only = tab02[
    ["numer_odcinka", "sdrr_total",
     "sdrr_motocykle", "sdrr_sam_osobowe", "sdrr_mikrobusy",
     "sdrr_lekkie_ciezarowe", "sdrr_ciezarowe_bez", "sdrr_ciezarowe_z",
     "sdrr_autobusy", "sdrr_ciagniki"]
]

# ---------------------------------------------------------------------------
# 3. Join
# ---------------------------------------------------------------------------

print("Joining Tab01 + Tab02 …")
gpr = tab01.merge(tab02_traffic_only, on="numer_odcinka", how="left")

unmatched = gpr["sdrr_total"].isna().sum()
print(f"  Joined: {len(gpr)} rows | Unmatched (no SDRR): {unmatched}")

# ---------------------------------------------------------------------------
# 4. Normalise road number for SKDR join
#    SKDR stores '000001D' — strip leading zeros + trailing letter → int
#    GPR stores 'A1', '1', '61', 'S7' — keep as-is for now, also make int version
#    Strategy: extract numeric part only
# ---------------------------------------------------------------------------

def road_num_int(val):
    """Extract the integer part of a road number: 'A1'->1, 'S7'->7, '61'->61."""
    import re
    if pd.isna(val):
        return pd.NA
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else pd.NA

gpr["nr_drogi_int"] = gpr["nr_drogi"].apply(road_num_int)

# ---------------------------------------------------------------------------
# 5. Use midpoint of right & left coordinates as the measurement point
# ---------------------------------------------------------------------------

gpr["lat"] = (gpr["lat_prawy"].fillna(gpr["lat_lewy"]) + gpr["lat_lewy"].fillna(gpr["lat_prawy"])) / 2
gpr["lon"] = (gpr["lon_prawy"].fillna(gpr["lon_lewy"]) + gpr["lon_lewy"].fillna(gpr["lon_prawy"])) / 2

no_coords = gpr["lat"].isna().sum()
print(f"  Rows with no coordinates: {no_coords}")

# ---------------------------------------------------------------------------
# 5b. Coerce sdrr_total to numeric (a handful of sub-section rows have strings)
# ---------------------------------------------------------------------------

gpr["sdrr_total"] = pd.to_numeric(gpr["sdrr_total"], errors="coerce")
bad = gpr["sdrr_total"].isna().sum()
if bad:
    print(f"  Note: {bad} rows with non-numeric sdrr_total (sub-sections) — kept as NaN")

# ---------------------------------------------------------------------------
# 6. Export CSV (full table, no geometry)
# ---------------------------------------------------------------------------

csv_path = OUTPUT_DIR / "gpr2025.csv"
gpr.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"Saved {csv_path}")

# ---------------------------------------------------------------------------
# 7. Export GeoPackage (points, WGS84)
# ---------------------------------------------------------------------------

gpr_with_coords = gpr.dropna(subset=["lat", "lon"]).copy()
geometry = [Point(lon, lat) for lon, lat in zip(gpr_with_coords["lon"], gpr_with_coords["lat"])]
gdf = gpd.GeoDataFrame(gpr_with_coords, geometry=geometry, crs="EPSG:4326")

gpkg_path = OUTPUT_DIR / "gpr2025.gpkg"
gdf.to_file(gpkg_path, layer="gpr2025_points", driver="GPKG")
print(f"Saved {gpkg_path}  ({len(gdf)} point features, EPSG:4326)")

# ---------------------------------------------------------------------------
# 8. Quick sanity check
# ---------------------------------------------------------------------------

print("\n--- Sanity check ---")
print(gpr[["numer_odcinka", "nr_drogi", "nr_drogi_int", "sdrr_total", "lat", "lon"]].head(5).to_string())
print(f"\nSDRR range: {gpr['sdrr_total'].min():.0f} – {gpr['sdrr_total'].max():.0f} poj./dobę")
roads = sorted(gpr["nr_drogi"].dropna().unique(), key=lambda x: str(x))
print(f"Roads ({len(roads)} unique): {roads[:20]} …")
