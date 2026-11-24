"""
03_pdf_sections2010.py — 2010 section geometry straight from GDDKiA's own 2010 map.

Mapa_SDR2010.pdf (data/raw/2010) is vector: every measured section is one grey polyline
(stroke 0.5 grey, 2.87 pt), 1,793 of them for 1,792 sections. The page coordinates are an
affine transform of PUWG 1992, fitted by ICP against today's national roads (median residual
~80 m; the larger residuals are exactly the 2010 alignments that have moved since).

Each line is matched to a section by an optimal assignment (Hungarian) on: distance from the
section's counting point (01_parse_gpr2010.py; by 2025 km or locality) to the line, and line
length vs the section's official length. Sections without a located point are matched to the
remaining lines by length next to their km-neighbours.

Replaces steps 02/03/03b for 2010. Reads output/gpr2010_sections.csv;
writes output/traffic_network_2010.gpkg layer 'sections' (+ 'skdr_unmeasured' empty).
"""
import pickle

import geopandas as gpd
import numpy as np
import pandas as pd
import pdfplumber
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import linemerge

import config

GREY = ((0.5, 0.5, 0.5), 2.87)
MAIN_X = 1150          # page x left of this = the three insets


def densify(a, step):
    out = []
    for p, q in zip(a[:-1], a[1:]):
        n = max(1, int(np.hypot(*(q - p)) / step))
        out.extend(p + (q - p) * t for t in np.linspace(0, 1, n, endpoint=False))
    out.append(a[-1])
    return np.array(out)


def page_lines():
    pdf_path = config.GPR2010_DIR / "Mapa_SDR2010.pdf"
    with pdfplumber.open(pdf_path) as pdf:
        p = pdf.pages[0]
        out = []
        for o in p.curves + p.lines:
            col = o.get("stroking_color")
            key = (tuple(round(c, 3) for c in col) if col else None, round(o.get("linewidth", 0), 2))
            if key == GREY and o.get("pts"):
                a = np.array(o["pts"], float)
                if a[:, 0].min() > MAIN_X and len(a) > 1:
                    out.append(a)
    return out


def fit_affine(lines):
    src = np.vstack([densify(g, 3) for g in lines])
    sk = gpd.read_file(config.SKDR_GPKG, layer="skdr_krajowe").to_crs(2180).explode(index_parts=False)
    dst = np.vstack([densify(np.asarray(g.coords)[:, :2], 400) for g in sk.geometry if g.length > 0])
    tree = cKDTree(dst)
    s0, s1, d0, d1 = src.min(0), src.max(0), dst.min(0), dst.max(0)
    sx, sy = (d1[0] - d0[0]) / (s1[0] - s0[0]), (d1[1] - d0[1]) / (s1[1] - s0[1])
    A = np.array([[sx, 0, d0[0] - sx * s0[0]], [0, -sy, d1[1] + sy * s0[1]]])
    X = np.c_[src, np.ones(len(src))]
    for thr in [20000] * 5 + [8000] * 5 + [3000] * 10 + [1500] * 10:
        d, k = tree.query(X @ A.T)
        m = d < thr
        A = np.linalg.lstsq(X[m], dst[k[m]], rcond=None)[0].T
    d, _ = tree.query(X @ A.T)
    print(f"PDF georeferenced: median residual {np.median(d):.0f} m, p75 {np.percentile(d, 75):.0f} m")
    return A


def main():
    raw = page_lines()
    A = fit_affine(raw)
    lines = [LineString(np.c_[g, np.ones(len(g))] @ A.T) for g in raw]
    L = np.array([ln.length / 1000 for ln in lines])
    print(f"2010 map lines: {len(lines)} ({L.sum():,.0f} km)")

    s = pd.read_csv(config.SECTIONS_CSV)
    s["dlugosc_km"] = s["dlugosc_km"].fillna(s["pik_konc"] - s["pik_pocz"]).fillna(1.0).clip(lower=0.1)
    n, m = len(s), len(lines)
    BIG = 1e6
    cost = np.full((n, m), BIG)
    from shapely.strtree import STRtree
    tree = STRtree(lines)
    has_pt = s.x.notna().values
    for i, r in enumerate(s.itertuples()):
        want = max(r.dlugosc_km, 0.3)
        if has_pt[i]:
            pt = Point(r.x, r.y)
            for j in tree.query(pt.buffer(6000)):
                d = lines[j].distance(pt) / 1000
                cost[i, j] = d * 2 + abs(np.log(max(L[j], 0.1) / want)) * 3
        else:   # no point: length only (weak), refined below by neighbours
            cost[i, :] = 50 + np.abs(np.log(np.maximum(L, 0.1) / want)) * 3
    cost = np.nan_to_num(cost, nan=BIG, posinf=BIG)
    rows, cols = linear_sum_assignment(cost)
    ok = cost[rows, cols] < BIG
    # second pass for point-less sections: near the matched lines of their km-neighbours
    s["line"] = -1
    s.loc[rows[ok], "line"] = cols[ok]
    s = s.sort_values(["system", "pik_pocz"])
    for idx in s.index[~has_pt[s.index]]:
        grp = s[s.system == s.system[idx]]
        pos = list(grp.index).index(idx)
        nb = [grp.index[k] for k in (pos - 1, pos + 1) if 0 <= k < len(grp)]
        nb_lines = [lines[s.line[k]] for k in nb if s.line[k] >= 0]
        if not nb_lines:
            continue
        taken = set(s.line[s.line >= 0]) - {s.line[idx]}
        want = max(s.dlugosc_km[idx], 0.3)
        best = None
        for j in range(m):
            if j in taken:
                continue
            d = min(lines[j].distance(nl) for nl in nb_lines) / 1000
            if d > 1:
                continue
            c = d + abs(np.log(max(L[j], 0.1) / want)) * 3
            if best is None or c < best[0]:
                best = (c, j)
        if best:
            s.loc[idx, "line"] = best[1]
    s = s.sort_index()
    matched = s[s.line >= 0].copy()
    matched["geometry"] = [lines[j] for j in matched.line]
    g = gpd.GeoDataFrame(matched, geometry="geometry", crs=2180)
    g["geom_km"] = (g.length / 1000).round(3)
    g["len_ratio"] = (g.geom_km / g.dlugosc_km).round(3)
    g["placement"] = "pdf_map"
    g["qa_flags"] = np.where(g.len_ratio.between(0.6, 1.6), "", "length")
    print(f"sections matched to a map line: {len(g)}/{n} ({g.dlugosc_km.sum():,.0f} of "
          f"{s.dlugosc_km.sum():,.0f} km); median length ratio {g.len_ratio.median():.2f}; "
          f"ratio outside 0.6–1.6: {(g.qa_flags == 'length').sum()}")
    keep = [c for c in ["numer_odcinka", "nr_drogi", "system", "road", "road_class",
                        "nazwa_odcinka", "pik_pocz", "pik_konc", "dlugosc_km", "status",
                        "sdrr_total", "sdrr_heavy", "heavy_share", "geom_km", "len_ratio",
                        "placement", "qa_flags", "geometry"] if c in g.columns]
    config.NETWORK_GPKG.unlink(missing_ok=True)
    g[keep].to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    gpd.GeoDataFrame(geometry=[], crs=2180).to_file(config.NETWORK_GPKG, layer="skdr_unmeasured",
                                                    driver="GPKG")
    print(f"saved {config.NETWORK_GPKG}")


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010")
    main()
