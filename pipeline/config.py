"""Paths and tuning constants shared by all pipeline steps."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = ROOT / "output"

YEAR = 2025
GPR_TAB01 = RAW / "Tab01_25_dk_KRAJ_20260414.xlsx"   # section list + counting points
GPR_TAB02 = RAW / "Tab02_25_dk_KRAJ_20260414.xlsx"   # SDRR by vehicle class

BDOT_ZIP = Path(r"D:\QGIS\BODT10k\Polska_SHP.zip")
import os
SKDR_GPKG = Path(os.environ.get("GPR_SKDR", DATA / "bdot" / "skdr_krajowe.gpkg"))
OSM_PBF = Path(r"D:\QGIS\osm_basemap\pbf\poland-latest.osm.pbf")  # Geofabrik extract
OSM_GPKG = DATA / "osm" / "osm_main_roads.gpkg"   # from 00b_fetch_osm.py (optional)
WEZLY_GPKG = Path(r"D:\QGIS\BODT10k\SKDR\skrw_wezly.gpkg")
BOUNDARY_SHP = Path(r"D:\QGIS\BODT10k\granice_admin.shp")

SECTIONS_CSV = OUT / f"gpr{YEAR}_sections.csv"
POINTS_GPKG = OUT / f"gpr{YEAR}_points.gpkg"
GRAPH_PKL = OUT / "skdr_graph.pkl"
NETWORK_GPKG = OUT / f"traffic_network_{YEAR}.gpkg"

# --- linear referencing --------------------------------------------------------
RUN_GAP_KM = 1.0          # chainage gap that splits one km-system into separate runs
ANCHOR_SNAP_M = 1500.0    # counting point must lie within this distance of the road
NODE_ROUND_M = 1.0        # endpoint rounding used to build graph topology
# routing cost multipliers per SKDR edge (relative to its length)
COST_SAME_ROAD = 1.0      # NUMER_DROG contains this road (e.g. 'S7' for system S7j)
COST_SAME_NUMBER = 1.3    # same number, other class (DK7 for S7 and vice versa)
COST_OTHER_ROAD = 3.0     # other national road (covers SKDR labelling errors)
# BDOT10k 'w budowie' pieces: routable only as a fallback. BDOT often marks bits of roads
# that GPR counted in 2025 (viaducts, rebuilt carriageways) as under construction, which
# would otherwise break the line; a counted GPR section is proof the road was open.
COST_NOT_OPERATIONAL = 2.5  # multiplies the road multiplier above
COST_OSM = 2.0  # OSM patch edges (roads BDOT10k lacks); multiplies the road multiplier
SCALE_OK = (0.75, 1.33)   # path length / chainage difference considered plausible

# SDRR colour classes (shared by the map renderer and the QGIS styles): upper bounds of
# each class (veh/day). Multi-hue sequential ramps generated in OKLCH with evenly falling
# (light theme) / rising (dark theme) lightness; line width encodes SDRR as well.
SDRR_BREAKS = [5_000, 10_000, 15_000, 20_000, 30_000, 50_000, 75_000, 100_000]
SDRR_COLORS_LIGHT = ["#ebc831", "#eca600", "#e78400", "#de6000", "#cf3a1f",
                     "#b3213d", "#91164b", "#6b174e", "#481645"]   # yellow → red → deep purple
SDRR_COLORS_DARK = ["#4270bd", "#786fd4", "#ad6bda", "#dd6bc8", "#ff73a6",
                    "#ff8981", "#ffa762", "#ffc75c", "#ffe772"]    # blue → violet → pink → orange → yellow
# roads without counts sit between the land colour and the lowest class in lightness
NO_COUNT_LIGHT, NO_COUNT_DARK = "#e2dfda", "#494843"
