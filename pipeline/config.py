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
SCALE_OK = (0.75, 1.33)   # path length / chainage difference considered plausible
