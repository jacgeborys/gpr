"""
04_make_s7_preview.py
Filter roads_gpr2025 to S7 for quick QGIS preview.

Reads:  output/roads_gpr2025.gpkg
Writes: output/s7_preview.gpkg
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString
from pathlib import Path

OUTPUT_DIR = Path("output")

roads = gpd.read_file(OUTPUT_DIR / "roads_gpr2025.gpkg", layer="roads_gpr2025")
s7    = roads[(roads["road_key"] == "S7") & (roads["join_method"] != "dummy")].copy()

matched = s7["sdrr_total"].notna()
print(f"S7 edges: {len(s7)}, matched: {matched.sum()}, "
      f"SDRR range: {s7['sdrr_total'].min():.0f}–{s7['sdrr_total'].max():.0f}")
print(f"Interchanges: {s7[['wezly_od','wezly_do']].head(10).to_string()}")

dummy = s7.iloc[[0]].copy()
dummy["sdrr_total"]    = 0
dummy["geometry"]      = LineString([(500000, 200000), (500001, 200000)])
dummy["gpr_odcinek"]   = None
dummy["dist_to_gpr_m"] = None
dummy["join_method"]   = "dummy"
s7 = pd.concat([s7, dummy], ignore_index=True)

out = OUTPUT_DIR / "s7_preview.gpkg"
s7.to_file(out, layer="s7", driver="GPKG")
print(f"Saved {out}")
