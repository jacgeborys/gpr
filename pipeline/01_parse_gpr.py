"""
01_parse_gpr.py — parse GDDKiA GPR Excel tables into clean section + piece tables.

GPR facts this step encodes:
  * nr_drogi is a chainage SYSTEM, not just a road: 'S7j', '94g', 'A1c' each have their
    own kilometrage. A road number with a suffix is still the same road (S7j → S7).
  * 226 sections span two systems, written as 'A1d\\nA1c' with matching
    'pik_pocz'/'pik_konc' lists. They are exploded into one PIECE per system.
  * pik_prawy/pik_lewy is the counting point's chainage; it anchors the section on the
    map. It normally falls inside one of the section's pieces (anchor piece).
  * Sections without SDRR carry the reason in 'uwagi' (opened Dec 2025, 2026 recount…).

Reads : config.GPR_TAB01, config.GPR_TAB02
Writes: output/gpr2025_sections.csv  one row per section (traffic + metadata)
        output/gpr2025_pieces.csv    one row per (section, chainage system) piece
        output/gpr2025_points.gpkg   counting points, EPSG:2180
"""
import geopandas as gpd
import numpy as np
import pandas as pd

import config
from common import road_class, system_base, to_float

TAB01_COLS = [
    "numer_odcinka", "nr_drogi", "nr_europejski", "pik_pocz", "pik_konc", "dlugosc_km",
    "nazwa_odcinka", "typ_odcinka", "pik_prawy", "pik_lewy", "miejscowosc",
    "lat_prawy", "lon_prawy", "y_cs92_prawy", "x_cs92_prawy",
    "lat_lewy", "lon_lewy", "y_cs92_lewy", "x_cs92_lewy",
    "nazwa_rejonu", "nr_rejonu", "pomiar_rozszerzony", "pomiar_jezdnie_dod",
    "pomiar_jezdnie_zakres", "pomiar_uzupelniajacy", "nr_stacji_scpr", "siec_tent",
    "odcinki_sasiednie", "odcinek_gpr2020", "uwagi", "nr_woj", "nr_kolejny",
]
TAB02_COLS = [
    "numer_odcinka", "nr_drogi", "nr_europejski", "pik_pocz", "pik_konc", "dlugosc_km",
    "nazwa_odcinka", "typ_odcinka", "sdrr_total", "sdrr_motocykle", "sdrr_sam_osobowe",
    "sdrr_mikrobusy", "sdrr_lekkie_ciezarowe", "sdrr_ciezarowe_bez", "sdrr_ciezarowe_z",
    "sdrr_autobusy", "sdrr_ciagniki", "nr_woj", "kolejnosc", "uwagi_tab02",
]
SDRR_COLS = [c for c in TAB02_COLS if c.startswith("sdrr_")]


def status(row):
    note = str(row["uwagi"]).lower() if pd.notna(row["uwagi"]) else ""
    if pd.isna(row["sdrr_total"]):
        if "oddany do ruchu" in note:
            return "opened_after_count"
        if "uzupełniaj" in note:
            return "pending_2026"
        if "nie prowadzono" in note:
            return "not_counted"
        return "no_data"
    if "może ulec zmianie" in note:
        return "provisional"
    return "measured"


SIDE_SPLIT_M = 1000  # right/left points further apart than this are two different places


def resolve_split_sides(s):
    """A few sections have their right and left counting points kilometres apart (two
    stations, or one with a wrong chainage); their mean lies off the road. Keep the side
    whose position agrees with the chainage of the neighbouring sections' points: the
    straight-line distance between two points cannot exceed their km difference."""
    side = {}
    for k in ("prawy", "lewy"):
        p = gpd.GeoSeries(gpd.points_from_xy(s[f"lon_{k}"], s[f"lat_{k}"]), crs=4326).to_crs(2180)
        side[k] = np.c_[p.x, p.y]
    gap = np.hypot(*(side["prawy"] - side["lewy"]).T)
    split = gap > SIDE_SPLIT_M
    p0 = s["pik_pocz"].map(lambda v: to_float(str(v).split("\n")[0]))
    s["side_used"] = np.where(s["lat"].notna(), "both", None)
    for i in np.flatnonzero(split):
        same = s.index[(s.system == s.system.iloc[i]) & ~split & s.x.notna()]
        nb = sorted(same, key=lambda j: abs(p0.loc[j] - p0.iloc[i]))[:2]
        best = None
        for k in ("prawy", "lewy"):
            xy, km = side[k][i], s[f"pik_{k}"].iloc[i]
            bad = sum(max(0.0, np.hypot(xy[0] - s.x.loc[j], xy[1] - s.y.loc[j])
                          - abs(km - s.pk.loc[j]) * 1000 * 1.05 - 300) for j in nb)
            if best is None or bad < best[0]:
                best = (bad, k, xy, km)
        _, k, xy, km = best
        r = s.index[i]
        s.loc[r, ["x", "y", "pk", "side_used"]] = [xy[0], xy[1], km, k]
        s.loc[r, ["lat", "lon"]] = [s.loc[r, f"lat_{k}"], s.loc[r, f"lon_{k}"]]
    print(f"sections with right/left counting points > {SIDE_SPLIT_M} m apart: {split.sum()} "
          f"(one side kept)")


def main():
    config.OUT.mkdir(exist_ok=True)
    t1 = pd.read_excel(config.GPR_TAB01, header=None, skiprows=11, names=TAB01_COLS)
    t2 = pd.read_excel(config.GPR_TAB02, header=None, skiprows=10, names=TAB02_COLS)
    for t in (t1, t2):
        t["numer_odcinka"] = pd.to_numeric(t["numer_odcinka"], errors="coerce")
        t.dropna(subset=["numer_odcinka"], inplace=True)
        t["numer_odcinka"] = t["numer_odcinka"].astype(int)
    s = t1.merge(t2[["numer_odcinka"] + SDRR_COLS], on="numer_odcinka", how="left")
    for c in SDRR_COLS:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    print(f"sections: {len(s)}  (Tab01 {len(t1)}, Tab02 {len(t2)})")

    s["nr_drogi"] = s["nr_drogi"].astype(str).str.strip()
    s["system"] = s["nr_drogi"].str.split("\n").str[0].str.strip()
    s["road"] = s["system"].map(lambda x: system_base(x)[0])
    s["road_class"] = s["road"].map(road_class)
    s["status"] = s.apply(status, axis=1)
    s["sdrr_heavy"] = s[["sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy",
                         "sdrr_ciagniki"]].sum(axis=1, min_count=1)
    s["heavy_share"] = (s["sdrr_heavy"] / s["sdrr_total"]).round(3)

    # counting point: mean of the right/left carriageway points
    for c in ("lat_prawy", "lon_prawy", "lat_lewy", "lon_lewy", "pik_prawy", "pik_lewy"):
        s[c] = s[c].map(to_float)
    s["lat"] = s[["lat_prawy", "lat_lewy"]].mean(axis=1)
    s["lon"] = s[["lon_prawy", "lon_lewy"]].mean(axis=1)
    s["pk"] = s[["pik_prawy", "pik_lewy"]].mean(axis=1)
    pts = gpd.GeoSeries(gpd.points_from_xy(s["lon"], s["lat"]), crs=4326).to_crs(2180)
    s["x"] = np.where(s["lat"].notna(), pts.x, np.nan)
    s["y"] = np.where(s["lat"].notna(), pts.y, np.nan)
    resolve_split_sides(s)

    # explode into chainage-system pieces
    pieces = []
    for _, r in s.iterrows():
        systems = [x.strip() for x in str(r["nr_drogi"]).split("\n")]
        p0s = [to_float(x) for x in str(r["pik_pocz"]).split("\n")]
        p1s = [to_float(x) for x in str(r["pik_konc"]).split("\n")]
        if not (len(systems) == len(p0s) == len(p1s)):
            print(f"  ! {r['numer_odcinka']}: cannot align systems {systems} with chainage")
            continue
        anchored = False
        for k, (sy, a, b) in enumerate(zip(systems, p0s, p1s)):
            is_anchor = (not anchored and pd.notna(r["pk"]) and a - 0.01 <= r["pk"] <= b + 0.01)
            anchored |= is_anchor
            road, num = system_base(sy)
            pieces.append(dict(numer_odcinka=r["numer_odcinka"], part=k, system=sy, road=road,
                               number=num, p0=a, p1=b, anchor=is_anchor))
    pieces = pd.DataFrame(pieces)
    s["pk_in_section"] = s["numer_odcinka"].isin(pieces.loc[pieces.anchor, "numer_odcinka"])

    # first-column-only chainage for the flat table
    s["pik_pocz"] = s["pik_pocz"].map(lambda v: to_float(str(v).split("\n")[0]))
    s["pik_konc"] = s["pik_konc"].map(lambda v: to_float(str(v).split("\n")[-1]))

    print("status:", s["status"].value_counts().to_dict())
    print(f"pieces: {len(pieces)} in {pieces['system'].nunique()} chainage systems; "
          f"sections whose counting-point km lies outside the section: {(~s.pk_in_section).sum()}")

    s.to_csv(config.SECTIONS_CSV, index=False, encoding="utf-8")
    pieces.to_csv(config.OUT / f"gpr{config.YEAR}_pieces.csv", index=False, encoding="utf-8")
    g = gpd.GeoDataFrame(s.dropna(subset=["x"]), geometry=gpd.points_from_xy(
        s.dropna(subset=["x"])["x"], s.dropna(subset=["x"])["y"]), crs=2180)
    g.to_file(config.POINTS_GPKG, layer="counting_points", driver="GPKG")
    print(f"saved {config.SECTIONS_CSV.name}, pieces csv, {config.POINTS_GPKG.name}")


if __name__ == "__main__":
    main()
