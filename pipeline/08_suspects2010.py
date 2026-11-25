"""
08_suspects2010.py — list likely wrong values on the 2010 map and draw a debug view of each.

Rules (on the map lines of 03_pdf_sections2010.py, neighbours = lines whose ends touch).
A line is *confirmed* when a label read on it is within one edit (a digit missed, added or
misread) of its value; confirmed lines are never suspects.
  label         a label read on the line is >= 2 edits from its value (exact table value)
  label_fuzzy   same, but the read is not a table value (weaker)
  jump          value differs >2x from every neighbour on the same road (>= 2 of them)
  short_high    line < 3 km whose value is > 2x every touching neighbour (or has none and > 15k)

Writes output/qa_suspects2010.csv and output/debug2010/NNN_<section>.png: left the original
GDDKiA map (Mapa_SDR2010.pdf) cropped to the same window, right our map with values.
Usage: set GPR_YEAR=2010; python 08_suspects2010.py [--no-maps] [--at lon,lat ...]
  --at draws only debug windows centred on the given points (output/debug2010/at_*.png).
"""
import importlib
import pickle
import sys

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

import config  # noqa: E402

TOUCH_M = 600
WIN_M = 14_000          # half-width of the debug window
OUT_DIR = config.OUT / "debug2010"


def touching(g):
    ends = np.array([c for ln in g.geometry for c in (ln.coords[0][:2], ln.coords[-1][:2])])
    nb = [set() for _ in range(len(g))]
    for a, b in cKDTree(ends).query_pairs(TOUCH_M):
        i, j = a // 2, b // 2
        if i != j:
            nb[i].add(j)
            nb[j].add(i)
    return nb


def edits(a, b):
    """Levenshtein distance."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def find(sec, ml):
    sec = sec.reset_index(drop=True)
    nb = touching(sec)
    v = sec.sdrr_total.values
    lab = ml.set_index("line")
    rows = []
    for i, r in sec.iterrows():
        if v[i] != v[i]:
            continue
        why = []
        val = str(int(v[i]))
        reads = []
        if r.line in lab.index and isinstance(lab.labels[r.line], str):
            reads = lab.labels[r.line].split(";")
        if reads and min(edits(val, t) for t in reads) <= 1:
            continue   # confirmed by the map's own label
        if reads:
            why.append(("label " if lab.label_exact[r.line] else "label_fuzzy ") + "/".join(reads))
        same = [j for j in nb[i] if sec.road[j] == r.road and v[j] == v[j]]
        if len(same) >= 2:
            q = v[i] / np.array([v[j] for j in same])
            if (q > 2).all() or (q < 0.5).all():
                why.append(f"jump x{np.exp(np.abs(np.log(q)).min()):.1f}")
        allnb = [j for j in nb[i] if v[j] == v[j]]
        if r.geom_km < 3:
            if (allnb and (v[i] > 2 * np.array([v[j] for j in allnb])).all()) or                     (not allnb and v[i] > 15000):
                why.append("short_high")
        allnb = [j for j in nb[i] if v[j] == v[j]]
        if why:
            rows.append(dict(idx=i, numer_odcinka=r.numer_odcinka, system=r.system, road=r.road,
                             nazwa=r.nazwa_odcinka, sdrr=int(v[i]), km=r.geom_km, line=r.line,
                             reasons="; ".join(why),
                             nb_values=",".join(str(int(v[j])) for j in sorted(allnb))))
    return sec, pd.DataFrame(rows)


def draw(sec, labels, sus, A, r06, centres=None):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(config.GPR2010_DIR / "Mapa_SDR2010.pdf"))
    page = doc[0]
    W, H = page.get_size()
    Ai = np.linalg.inv(np.vstack([A, [0, 0, 1]]))[:2]
    OUT_DIR.mkdir(exist_ok=True)
    for f in OUT_DIR.glob("at_*.png" if centres else "[0-9]*.png"):
        f.unlink()
    from shapely.geometry import Point
    for n, s in enumerate(sus.itertuples()):
        g = sec.geometry[s.idx] if s.idx >= 0 else None
        c = g.interpolate(0.5, normalized=True) if g is not None else Point(s.cx, s.cy)
        x0, x1, y0, y1 = c.x - WIN_M, c.x + WIN_M, c.y - WIN_M, c.y + WIN_M
        # PDF crop: window corners → page points (page y grows downwards in pdfplumber)
        pc = np.c_[[x0, x1, x1, x0], [y0, y0, y1, y1], np.ones(4)] @ Ai.T
        l, rgt, t, b = pc[:, 0].min(), pc[:, 0].max(), pc[:, 1].min(), pc[:, 1].max()
        im = page.render(scale=900 / (rgt - l), crop=(l, H - b, W - rgt, t)).to_pil()
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 7.2), dpi=110)
        a1.imshow(im, extent=(x0, x1, y0, y1))
        a1.set_title("GDDKiA Mapa SDR 2010", fontsize=10)
        win = sec.cx[x0 - 5000:x1 + 5000, y0 - 5000:y1 + 5000]
        win = win[win.sdrr_total.notna()].sort_values("sdrr_total")
        segs, ws, cs = [], [], []
        for gg, val in zip(win.geometry, win.sdrr_total):
            for p in r06.segs(gg):
                segs.append(p)
                ws.append(r06.width(val))
                cs.append(r06.smooth_color(val, config.SDRR_COLORS_LIGHT))
        a2.add_collection(LineCollection(segs, linewidths=ws, colors=cs, capstyle="round", zorder=2))
        for p in (r06.segs(g) if g is not None else []):
            a2.plot(p[:, 0], p[:, 1], color="#00b4ff", lw=r06.width(s.sdrr) + 5, alpha=0.45,
                    zorder=1, solid_capstyle="round")
        for i2, rr in win.iterrows():
            m = rr.geometry.interpolate(0.5, normalized=True)
            a2.annotate(f"{int(rr.sdrr_total)}", (m.x, m.y), fontsize=7.5, ha="center",
                        color="#c00000" if i2 == s.idx else "#111", zorder=5,
                        fontweight="bold" if i2 == s.idx else "normal",
                        path_effects=[matplotlib.patheffects.withStroke(linewidth=2, foreground="w")])
        lw_ = labels.cx[x0:x1, y0:y1]
        for rr in lw_.itertuples():
            a2.annotate(rr.label, (rr.geometry.x, rr.geometry.y), fontsize=6.5, color="#0050c8",
                        ha="center", va="top", xytext=(0, -6), textcoords="offset points",
                        style="italic" if not rr.exact else "normal", zorder=4)
        a2.set_title("ours: black = assigned SDR, blue = label read on the map "
                     "(italic = not a table value)", fontsize=9)
        for a in (a1, a2):
            a.set_xlim(x0, x1)
            a.set_ylim(y0, y1)
            a.set_aspect("equal")
            a.set_xticks([])
            a.set_yticks([])
        fig.suptitle(f"#{n}  {s.numer_odcinka}  {s.system}  {s.nazwa}  SDR {s.sdrr}  "
                     f"({s.km} km)  —  {s.reasons}", fontsize=10)
        fig.tight_layout()
        fig.savefig(OUT_DIR / (f"at_{n}.png" if centres else f"{n:03d}_{s.numer_odcinka}.png"))
        plt.close(fig)
    print(f"debug maps: {OUT_DIR} ({len(sus)})")


def main():
    import matplotlib.patheffects  # noqa: F401
    import fiona
    # the map's own line shapes (step 03c replaces 'sections' with real road shapes)
    lay = "sections_pdf" if "sections_pdf" in fiona.listlayers(config.NETWORK_GPKG) else "sections"
    sec = gpd.read_file(config.NETWORK_GPKG, layer=lay)
    ml = gpd.read_file(config.NETWORK_GPKG, layer="map_lines")
    labels = gpd.read_file(config.NETWORK_GPKG, layer="map_labels")
    with open(config.OUT / "pdf2010_cache.pkl", "rb") as f:
        A = pickle.load(f)["A"]
    r06 = importlib.import_module("06_render_cartogram")
    if "--at" in sys.argv:
        ll = [tuple(map(float, a.split(","))) for a in sys.argv[sys.argv.index("--at") + 1:]]
        pts = gpd.GeoSeries(gpd.points_from_xy(*zip(*ll)), crs=4326).to_crs(2180)
        at = pd.DataFrame(dict(idx=-1, cx=pts.x, cy=pts.y, numer_odcinka="", system="",
                               nazwa=[f"{a:.3f},{b:.3f}" for a, b in ll], sdrr=0, km=0,
                               reasons="--at"))
        draw(sec.reset_index(drop=True), labels, at, A, r06, centres=True)
        return
    sec, sus = find(sec, ml)
    out = config.OUT / "qa_suspects2010.csv"
    sus.drop(columns="idx").to_csv(out, index=False)
    kinds = sus.reasons.str.findall(r"(jump|label_fuzzy|label|short_high)").explode().value_counts()
    print(f"suspects: {len(sus)} sections → {out}\n{kinds.to_string()}")
    if "--no-maps" not in sys.argv:
        draw(sec, labels, sus, A, r06)


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010")
    main()
