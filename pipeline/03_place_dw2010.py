"""
03_place_dw2010.py — place the GPR 2010 regional sections on today's regional roads by km.

Regional roads barely changed course since 2010 and mostly kept their km numbering, so a 2010
section [pik_pocz, pik_konc] on road R is cut out of the 2025 regional sections of road R
(step 03 with GPR_NET=dw), which carry both km and real geometry:
  * the 2025 sections of one system are merged into continuous lines (parts);
  * on each part the 2025 section ends give (km, distance along the part) pairs, so km map to
    positions piecewise linearly (local differences between GDDKiA km and BDOT length are
    absorbed, as in the 2025 placement);
  * the 2010 km range is cut out of every part it overlaps.
Quality: `len_ratio` = placed length / 2010 length; outside 0.67–1.5 → qa_flags 'scale' (the
km numbering changed there, e.g. a new bypass). Sections on roads that are no longer regional
(now national, or gone) are left out and listed.

Reads : output/gpr2010_dw_sections.csv (01_parse_gpr2010_dw.py),
        output/traffic_network_2025_dw.gpkg layer 'sections'
Writes: output/traffic_network_2010_dw.gpkg layer 'sections'
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, substring, unary_union

import config

SRC_2010 = config.OUT / "gpr2010_dw_sections.csv"
REF_2025 = config.OUT / "traffic_network_2025_dw.gpkg"
OUT = config.OUT / "traffic_network_2010_dw.gpkg"
ON_PART_M = 30      # a 2025 section lies on a merged part if its middle is this close
SCALE_OK = (0.67, 1.5)


def lines_of(g):
    if g is None or g.is_empty:
        return []
    return list(g.geoms) if g.geom_type == "MultiLineString" else [g]


def km_parts(ref):
    """For one chainage system: merged parts, each with sorted (km, distance) pairs."""
    u = unary_union([ln for g in ref.geometry for ln in lines_of(g)])
    merged = linemerge(u) if u.geom_type == "MultiLineString" else u
    out = []
    for part in lines_of(merged):
        pairs = []
        for g, a, b in zip(ref.geometry, ref.pik_pocz, ref.pik_konc):
            ls = lines_of(g)
            if not ls or part.distance(g.interpolate(0.5, normalized=True)) > ON_PART_M:
                continue
            p0, p1 = Point(ls[0].coords[0]), Point(ls[-1].coords[-1])
            pairs += [(a, part.project(p0)), (b, part.project(p1))]
        if len(pairs) < 2:
            continue
        pairs = sorted(set(pairs))
        km = np.array([p[0] for p in pairs])
        d = np.array([p[1] for p in pairs])
        # one distance per km (two sections meeting at a km give the same point)
        u, idx = np.unique(km, return_index=True)
        out.append((part, u, d[idx]))
    return out


def main():
    s = pd.read_csv(SRC_2010, dtype={"numer_odcinka": str, "nr_drogi": str, "road": str})
    ref = gpd.read_file(REF_2025, layer="sections")
    ref = ref[ref.geometry.notna() & ref.pik_pocz.notna() & ref.pik_konc.notna()]
    ref["system"] = ref["system"].astype(str)
    parts = {sy: km_parts(g) for sy, g in ref.groupby("system")}
    rows, missing = [], []
    for r in s.itertuples():
        sy = r.nr_drogi if r.nr_drogi in parts else r.road
        pieces = []
        for part, km, d in parts.get(sy, []):
            a, b = max(r.pik_pocz, km[0]), min(r.pik_konc, km[-1])
            if b - a < 0.05:
                continue
            d0, d1 = np.interp(a, km, d), np.interp(b, km, d)
            if abs(d1 - d0) > 1:
                pieces.append(substring(part, min(d0, d1), max(d0, d1)))
        if not pieces:
            missing.append(r)
            continue
        geom = pieces[0] if len(pieces) == 1 else MultiLineString(
            [ln for p in pieces for ln in lines_of(p)])
        rows.append(dict(r._asdict(), geometry=geom))
    g = gpd.GeoDataFrame(pd.DataFrame(rows).drop(columns="Index"), geometry="geometry", crs=2180)
    g["geom_km"] = (g.length / 1000).round(3)
    g["len_ratio"] = (g.geom_km / g.dlugosc_km.clip(lower=0.1)).round(3)
    g["qa_flags"] = np.where(g.len_ratio.between(*SCALE_OK), "", "scale")
    m = pd.DataFrame(missing)
    print(f"2010 regional sections placed: {len(g)}/{len(s)} ({g.dlugosc_km.sum():,.0f} of "
          f"{s.dlugosc_km.sum():,.0f} km); length ratio outside {SCALE_OK}: "
          f"{(g.qa_flags == 'scale').sum()}")
    if len(m):
        print(f"not placed: {len(m)} sections on {m.road.nunique()} roads "
              f"({m.dlugosc_km.sum():,.0f} km); roads: {', '.join(sorted(m.road.unique(), key=int)[:40])}")
    OUT.unlink(missing_ok=True)
    g.to_file(OUT, layer="sections", driver="GPKG")
    if len(m):
        m.drop(columns="Index").to_csv(config.OUT / "gpr2010_dw_unplaced.csv", index=False)
    print(f"saved {OUT.name}")


if __name__ == "__main__":
    main()
