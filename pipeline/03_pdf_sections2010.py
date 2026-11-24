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
GREEN = (0.645, 0.992, 0.629)
MAIN_X = 1150
TOUCH_M = 600          # two map lines whose ends are this close are consecutive          # page x left of this = the three insets


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
        out, green = [], []
        size = (p.width, p.height)
        for o in p.curves + p.lines:
            col = o.get("stroking_color")
            key = (tuple(round(c, 3) for c in col) if col else None, round(o.get("linewidth", 0), 2))
            if not o.get("pts"):
                continue
            if key == GREY:
                a = np.array(o["pts"], float)
                if a[:, 0].min() > MAIN_X and len(a) > 1:
                    out.append(a)
            elif key[0] == GREEN:
                green.append((key[1], o["pts"]))
    return out, green, size


def band_widths(lines, green, size, S=3.0):
    """Width (pt) of the green SDR band around each grey line: GDDKiA draws the band width ∝
    SDR, so it tells which line carries which traffic. Rasterize the band, cast rays
    perpendicular to the line every 4 pt, take the median."""
    from PIL import Image, ImageDraw
    img = Image.new("L", (int(size[0] * S) + 1, int(size[1] * S) + 1), 0)
    dr = ImageDraw.Draw(img)
    for lw, pts in green:
        dr.line([(x * S, y * S) for x, y in pts], fill=255, width=max(1, int(round(max(lw, 0.5) * S))))
    Gm = np.array(img) > 0
    out = []
    for g in lines:
        ws = []
        for a, b in zip(g[:-1], g[1:]):
            seg = b - a
            Ls = np.hypot(*seg)
            if Ls < 1e-6:
                continue
            nrm = np.array([-seg[1], seg[0]]) / Ls
            for f in np.arange(0.5, max(Ls, 1), 4.0) / max(Ls, 1):
                q0 = a + seg * min(f, 1)
                w = 0.0
                for side in (1, -1):
                    d = 0.0
                    while d < 60:
                        x, y = ((q0 + nrm * side * d) * S).astype(int)
                        if not (0 <= y < Gm.shape[0] and 0 <= x < Gm.shape[1]) or not Gm[y, x]:
                            break
                        d += 0.25
                    w += d
                ws.append(w)
        out.append(np.median(ws) if ws else np.nan)
    return np.array(out)


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


def chain_bonus(s, lines, cost, touch_m=TOUCH_M, k_cand=40, jump=8.0, bonus=10.0):
    """Continuity: sections with consecutive km on one road must lie on lines that touch on the
    map. For each run of consecutive sections, pick the best sequence of lines (Viterbi over the
    k_cand cheapest lines per section; a jump between non-touching lines costs `jump`), then
    make the chosen pairs `bonus` cheaper for the global assignment."""
    from scipy.spatial import cKDTree
    ends = np.array([c for ln in lines for c in (ln.coords[0][:2], ln.coords[-1][:2])])
    tr = cKDTree(ends)
    touch = [set() for _ in lines]
    for a, b in tr.query_pairs(touch_m):
        i, j = a // 2, b // 2
        if i != j:
            touch[i].add(j)
            touch[j].add(i)
    order = s.reset_index().sort_values(["system", "pik_pocz"])
    runs, cur, prev = [], [], None
    for r in order.itertuples():
        if prev is not None and (r.system != prev.system or r.pik_pocz - prev.pik_konc > 1.0):
            runs.append(cur)
            cur = []
        cur.append(r.index)
        prev = r
    runs.append(cur)
    out = cost.copy()
    n_pref = 0
    for run in runs:
        if len(run) < 2:
            continue
        cands = [list(np.argsort(cost[i])[:k_cand]) for i in run]
        # include lines touching the previous section's candidates
        best = [{j: (cost[run[0], j], None) for j in cands[0]}]
        for t_ in range(1, len(run)):
            i = run[t_]
            cand = set(cands[t_])
            for j in list(best[-1])[:k_cand]:
                cand |= touch[j]
            layer = {}
            for j in cand:
                u = cost[i, j]
                bp, bc = None, np.inf
                for pj, (pc, _) in best[-1].items():
                    if pj == j:
                        continue
                    c = pc + (0.0 if j in touch[pj] else jump)
                    if c < bc:
                        bc, bp = c, pj
                layer[j] = (bc + u, bp)
            best.append(layer)
        j = min(best[-1], key=lambda x: best[-1][x][0])
        seq = [j]
        for layer in reversed(best[1:]):
            j = layer[j][1]
            seq.append(j)
        seq = seq[::-1]
        for i, j in zip(run, seq):
            out[i, j] -= bonus
            n_pref += 1
    print(f"continuity: {len(runs)} runs, {n_pref} section→line preferences from chains")
    return out


def main():
    raw, green, size = page_lines()
    A = fit_affine(raw)
    lines = [LineString(np.c_[g, np.ones(len(g))] @ A.T) for g in raw]
    L = np.array([ln.length / 1000 for ln in lines])
    bw = band_widths(raw, green, size)
    bw = np.where(np.isnan(bw), np.nanmedian(bw), bw)
    print(f"2010 map lines: {len(lines)} ({L.sum():,.0f} km); band width median {np.median(bw):.1f} pt")

    s = pd.read_csv(config.SECTIONS_CSV)
    s["dlugosc_km"] = s["dlugosc_km"].fillna(s["pik_konc"] - s["pik_pocz"]).fillna(1.0).clip(lower=0.1)
    n, m = len(s), len(lines)
    # band width → SDR by quantile matching (the 1,793 lines are the 1,792 sections)
    sdr_sorted = np.sort(s.sdrr_total.fillna(s.sdrr_total.median()).values)
    rank = bw.argsort().argsort() / max(m - 1, 1)
    sdr_est = np.interp(rank, np.linspace(0, 1, n), sdr_sorted)
    # dense cost: distance from the counting point (km), length, SDR vs band
    xs, ys = s.x.values, s.y.values
    has_pt = ~np.isnan(xs)
    mids = np.array([[ln.interpolate(0.5, normalized=True).x, ln.interpolate(0.5, normalized=True).y]
                     for ln in lines])
    from shapely.strtree import STRtree
    tree = STRtree(lines)
    dist = np.full((n, m), 30.0)   # unknown / far: flat 30 km
    for i in np.flatnonzero(has_pt):
        pt = Point(xs[i], ys[i])
        for j in tree.query(pt.buffer(30000)):
            dist[i, j] = lines[j].distance(pt) / 1000
    want = s.dlugosc_km.values[:, None]
    sdr = s.sdrr_total.fillna(s.sdrr_total.median()).values[:, None]
    cost = (1.5 * dist + 3 * np.abs(np.log(np.maximum(L, 0.1)[None, :] / want))
            + 2 * np.abs(np.log(sdr_est[None, :] / sdr)))
    cost = np.nan_to_num(cost, nan=1e3, posinf=1e3)
    cost = chain_bonus(s, lines, cost)
    rows, cols = linear_sum_assignment(cost)
    s["line"] = -1
    s.loc[rows, "line"] = cols
    s["match_cost"] = np.nan
    s.loc[rows, "match_cost"] = cost[rows, cols]
    s["sdr_band"] = np.nan
    s.loc[rows, "sdr_band"] = sdr_est[cols].round()
    r = np.corrcoef(np.log(s.sdrr_total[rows]), np.log(sdr_est[cols]))[0, 1]
    print(f"assigned {len(rows)} sections; log-SDR vs band-width correlation {r:.2f}")
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
                        "placement", "qa_flags", "match_cost", "sdr_band", "geometry"] if c in g.columns]
    config.NETWORK_GPKG.unlink(missing_ok=True)
    g[keep].to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    gpd.GeoDataFrame(geometry=[], crs=2180).to_file(config.NETWORK_GPKG, layer="skdr_unmeasured",
                                                    driver="GPKG")
    print(f"saved {config.NETWORK_GPKG}")


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010")
    main()
