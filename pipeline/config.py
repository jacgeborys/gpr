"""Paths and tuning constants shared by all pipeline steps."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = ROOT / "output"

import os
# which GPR round the pipeline works on (2025 by default); `set GPR_YEAR=2010` runs the
# 2010 round through the same steps (01_parse_gpr2010.py instead of 01_parse_gpr.py)
YEAR = int(os.environ.get("GPR_YEAR", 2025))
AUTHOR = "Jacek Gęborys"   # credited in the map footer
# which road network: 'dk' national roads (default), 'dw' regional roads (drogi wojewódzkie,
# GPR 2025 only): `set GPR_NET=dw` runs steps 01–03b on the regional tables and BDOT regional
# roads into separate files (gpr2025_dw_*, traffic_network_2025_dw.gpkg)
NET = os.environ.get("GPR_NET", "dk")
TAG = f"{YEAR}" + ("_dw" if NET == "dw" else "")
GPR_TAB01 = RAW / "Tab01_25_dk_KRAJ_20260414.xlsx"   # section list + counting points
GPR_TAB02 = RAW / "Tab02_25_dk_KRAJ_20260414.xlsx"   # SDRR by vehicle class
GPR_DW_TAB01 = RAW / "Tab01_25_dw_KRAJ.xlsx"         # regional roads: sections + counting points
GPR_DW_TAB02 = RAW / "Tab02_25_dw_KRAJ.xlsx"         # regional roads: SDRR

BDOT_ZIP = Path(r"D:\QGIS\BODT10k\Polska_SHP.zip")
SKDR_GPKG = Path(os.environ.get("GPR_SKDR", DATA / "bdot" / "skdr_krajowe.gpkg"))
OSM_PBF = Path(r"D:\QGIS\osm_basemap\pbf\poland-latest.osm.pbf")  # Geofabrik extract
OSM_GPKG = DATA / "osm" / "osm_main_roads.gpkg"   # from 00b_fetch_osm.py (optional)
WEZLY_GPKG = Path(r"D:\QGIS\BODT10k\SKDR\skrw_wezly.gpkg")
DW_GPKG = Path(r"D:\QGIS\BODT10k\SKDR\skdr_wojewodzkie.gpkg")   # regional roads (BDOT10k)
BOUNDARY_SHP = Path(r"D:\QGIS\BODT10k\granice_admin.shp")
LAND_SHP = Path(r"D:\QGIS\dual_carriegeways\data\countries.shp")   # Natural Earth, land only

SECTIONS_CSV = OUT / f"gpr{TAG}_sections.csv"
PIECES_CSV = OUT / f"gpr{TAG}_pieces.csv"
POINTS_GPKG = OUT / f"gpr{TAG}_points.gpkg"
GRAPH_PKL = OUT / ("skdr_graph.pkl" if TAG == "2025" else f"skdr_graph_{TAG}.pkl")
NETWORK_GPKG = OUT / f"traffic_network_{TAG}.gpkg"
DW_NETWORK_GPKG = OUT / f"traffic_network_{YEAR}_dw.gpkg"   # regional sections (GPR_NET=dw)
GPR2010_DIR = RAW / "2010"   # Wykaz odcinków (Tablica 1) + SDR (Tablica 2) PDFs from the archive

# --- linear referencing --------------------------------------------------------
RUN_GAP_KM = 1.0          # chainage gap that splits one km-system into separate runs
ANCHOR_SNAP_M = 1500.0    # counting point must lie within this distance of the road
NODE_ROUND_M = 1.0        # endpoint rounding used to build graph topology
# routing cost multipliers per SKDR edge (relative to its length)
COST_SAME_ROAD = 1.0      # NUMER_DROG contains this road (e.g. 'S7' for system S7j)
COST_SAME_NUMBER = 1.3    # same number, other class (DK7 for S7 and vice versa)
COST_OTHER_ROAD = 3.0     # other national road (covers SKDR labelling errors)
COST_OTHER_ROAD_PAST = 1.4  # past GPR rounds: roads were renumbered since, so other numbers are fine
COST_REGIONAL_PAST = 2.5    # past rounds: regional roads (old national alignments downgraded)
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

# cities with powiat rights (miasta na prawach powiatu): they manage the national roads
# inside them, which GPR does not count; drawn as pale areas on the map
POWIAT_CITIES = [
    "Biała Podlaska", "Białystok", "Bielsko-Biała", "Bydgoszcz", "Bytom", "Chełm", "Chorzów",
    "Częstochowa", "Dąbrowa Górnicza", "Elbląg", "Gdańsk", "Gdynia", "Gliwice",
    "Gorzów Wielkopolski", "Grudziądz", "Jastrzębie-Zdrój", "Jaworzno", "Jelenia Góra", "Kalisz",
    "Katowice", "Kielce", "Konin", "Koszalin", "Kraków", "Krosno", "Legnica", "Leszno", "Lublin",
    "Łomża", "Łódź", "Mysłowice", "Nowy Sącz", "Olsztyn", "Opole", "Ostrołęka", "Piekary Śląskie",
    "Piotrków Trybunalski", "Płock", "Poznań", "Przemyśl", "Radom", "Ruda Śląska", "Rybnik",
    "Rzeszów", "Siedlce", "Siemianowice Śląskie", "Skierniewice", "Słupsk", "Sopot", "Sosnowiec",
    "Suwałki", "Szczecin", "Świętochłowice", "Świnoujście", "Tarnobrzeg", "Tarnów", "Toruń",
    "Tychy", "Wałbrzych", "Warszawa", "Włocławek", "Wrocław", "Zabrze", "Zamość", "Zielona Góra",
    "Żory"]
