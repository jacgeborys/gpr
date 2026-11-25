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
MAIN_X = 1000            # page x left of this = the Warsaw and Poznań insets (the main map's
                         # west edge, Szczecin–Chojna–Kostrzyn, reaches x ≈ 1080)
UNASSIGNED = 40.0        # cost of leaving a section off the map (≈ a line 25 km away)
LABEL_FAR_KM = 25       # a label this far from a section's counting point is not its label
TOUCH_M = 600            # two map lines whose ends are this close are consecutive
# page boxes (x0, x1, y0, y1) right of MAIN_X that are not the main map: the edge of the
# Górnośląski inset, the legend (with an example label '8511') and the credits box
NOT_MAIN = [(MAIN_X, 1262, 1705, 2551), (1300, 1500, 2000, 2551), (1700, 2050, 2220, 2551)]
CACHE = config.OUT / "pdf2010_cache.pkl"   # parsed PDF (lines, band, glyphs, affine): ~4 min to rebuild


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
        out, green, glyph = [], [], []
        size = (p.width, p.height)
        for o in p.curves:
            col = o.get("non_stroking_color")
            if o.get("fill") and col and tuple(round(c, 3) for c in col) == (0, 0, 0) and o.get("pts"):
                a = np.array(o["pts"], float)
                if a[:, 0].min() >= MAIN_X and max(np.ptp(a, 0)) <= 9:
                    glyph.append(a)
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
    return out, green, size, glyph


def off_main(a):
    x, y = a.mean(0)
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in NOT_MAIN)


def load_pdf():
    """Parse the PDF once (grey lines, band widths, glyph pieces, georeference) and cache it."""
    src = config.GPR2010_DIR / "Mapa_SDR2010.pdf"
    if CACHE.exists() and CACHE.stat().st_mtime > src.stat().st_mtime:
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    raw, green, size, glyph = page_lines()
    A = fit_affine([a for a in raw if not off_main(a)])   # inset lines would skew the fit
    bw = band_widths(raw, green, size)
    d = dict(raw=raw, size=size, glyph=glyph, A=A, bw=bw)
    with open(CACHE, "wb") as f:
        pickle.dump(d, f)
    return d


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


def read_map_labels(s, raw, glyph, A, max_pt=14.0):
    """The SDR values printed on the map (pdf_labels2010), each tied to the nearest grey line.
    Labels that do not read as a table value are decoded against the values of sections whose
    counting point is near the label. → DataFrame px, py, label, exact, how, line, x, y."""
    import pdf_labels2010 as pl
    from shapely.strtree import STRtree
    vals = s.sdrr_total.dropna().astype(int).astype(str)
    Ai = np.linalg.inv(np.vstack([A, [0, 0, 1]]))[:2]
    has = s.x.notna() & s.sdrr_total.notna()
    pxy = np.c_[s.x[has], s.y[has], np.ones(has.sum())] @ Ai.T
    pv = vals[has].values
    ptree = cKDTree(pxy)
    nopt = list(vals[~s.x.notna() & s.sdrr_total.notna()])

    def cands(x, y):
        return [pv[k] for k in ptree.query_ball_point((x, y), pl.NEAR_PT)] + nopt

    reads = pl.read_labels(glyph, set(vals), cands)
    rl = [LineString(g) for g in raw]
    tr = STRtree(rl)
    lab = pd.DataFrame(reads, columns=["px", "py", "label", "exact", "how"])
    lab["line"] = -1
    for k, (x, y) in enumerate(zip(lab.px, lab.py)):
        q = Point(x, y)
        hits = [j for j in tr.query(q.buffer(max_pt)) if rl[j].distance(q) <= max_pt]
        if hits:
            lab.loc[k, "line"] = min(hits, key=lambda j: rl[j].distance(q))
    # a label between two parallel lines can go to the wrong one (A4a / DK94 at Bolesławiec):
    # when one line gets exact labels of two values, the farther label moves to the next line
    # within reach that has no exact label
    n_moved = 0
    for j, g in lab[(lab.line >= 0) & lab.exact].groupby("line"):
        if g.label.nunique() < 2:
            continue
        dist = {k: rl[j].distance(Point(lab.px[k], lab.py[k])) for k in g.index}
        keep = min(dist, key=dist.get)
        for k in g.index:
            if lab.label[k] == lab.label[keep]:
                continue
            q = Point(lab.px[k], lab.py[k])
            taken = set(lab.line[lab.exact & (lab.line >= 0)])
            alt = [i for i in tr.query(q.buffer(max_pt * 1.5))
                   if i != j and i not in taken and rl[i].distance(q) <= max_pt * 1.5]
            if alt:
                lab.loc[k, "line"] = min(alt, key=lambda i: rl[i].distance(q))
                n_moved += 1
    xy = np.c_[lab.px, lab.py, np.ones(len(lab))] @ A.T
    lab["x"], lab["y"] = xy[:, 0], xy[:, 1]
    print(f"map labels read: {len(lab)} {lab.how.value_counts().to_dict()}; "
          f"on a line: {(lab.line >= 0).sum()} ({n_moved} moved off a line with another label)")
    return lab


def fix_points(s, lab, far_km=LABEL_FAR_KM):
    """Counting points vs the map's own labels. A section whose value is unique in the table and
    read on the map: with no point, or a point located by locality name (a namesake village
    can be hundreds of km away) far from every reading of its value, the point moves to the
    label. Points from the 2025 chainage are trusted: a far reading is a misread."""
    s = s.copy()
    ex = lab[lab.exact & (lab.line >= 0)]
    cnt = s.sdrr_total.dropna().astype(int).astype(str).value_counts()
    moved = added = 0
    for i, r in s.iterrows():
        if r.sdrr_total != r.sdrr_total:
            continue
        v = str(int(r.sdrr_total))
        if cnt[v] > 1:
            continue
        rd = ex[ex.label == v]
        if rd.empty:
            continue
        if r.x == r.x:
            d = np.hypot(rd.x - r.x, rd.y - r.y) / 1000
            if d.min() <= far_km or r.located_by == "chainage_2025":
                continue
        if np.ptp(rd.x) > 10_000 or np.ptp(rd.y) > 10_000:
            continue   # several readings far apart: ambiguous
        moved += r.x == r.x
        added += r.x != r.x
        s.loc[i, ["x", "y", "located_by"]] = rd.x.mean(), rd.y.mean(), "map_label"
    print(f"counting points from map labels: {moved} locality points moved, {added} added")
    return s


def neighbour_points(s, far_km=60.0):
    """Sections next to each other in km (same chainage system) are next to each other on the
    map. A section with no point gets the mean of its neighbours' points; a locality point far
    (> far_km) from neighbours that agree with each other is a namesake village and is replaced
    the same way. Only trusted neighbours count (2025 chainage, map label)."""
    s = s.copy()
    order = s.sort_values(["system", "pik_pocz"]).index
    prev_, next_ = {}, {}
    for a_, b_ in zip(order[:-1], order[1:]):
        if s.system[a_] == s.system[b_] and abs(s.pik_pocz[b_] - s.pik_konc[a_]) <= 1.0:
            next_[a_], prev_[b_] = b_, a_
    trusted = s.located_by.isin(["chainage_2025", "map_label"])
    n_fix = n_add = 0
    for _ in range(3):   # chains of sections without points fill in from both ends
        for i in s.index:
            nb = [k for k in (prev_.get(i), next_.get(i)) if k is not None and s.x[k] == s.x[k]
                  and (trusted[k] or s.located_by[k] == "neighbours")]
            if not nb:
                continue
            xy = np.array([[s.x[k], s.y[k]] for k in nb])
            if s.x[i] != s.x[i]:
                s.loc[i, ["x", "y", "located_by"]] = *xy.mean(0), "neighbours"
                n_add += 1
            elif s.located_by[i] == "locality" and len(nb) == 2 and                     np.hypot(*(xy[0] - xy[1])) < far_km * 1000 and                     np.hypot(*(xy.mean(0) - [s.x[i], s.y[i]])) > far_km * 1000:
                s.loc[i, ["x", "y", "located_by"]] = *xy.mean(0), "neighbours"
                n_fix += 1
    print(f"counting points from km-neighbours: {n_add} added, {n_fix} far locality points replaced; "
          f"still without a point: {s.x.isna().sum()}")
    return s


def label_bonus(s, lab, lines, cost, exact_bonus=120.0, near_bonus=20.0, reserve=80.0,
                far_km=LABEL_FAR_KM):
    """A line whose label reads as a section's SDR (exact match with the 2010 table) is that
    section's line, if the label is near the section's counting point (or it has none), or if
    a km-neighbour's value is read on a line touching it (the point is wrong then). A near-miss
    reading (one digit off) gives a smaller bonus. A line read as a value that only one section
    has is reserved for it: other sections pay `reserve` to take it."""
    import importlib
    edits = importlib.import_module("08_suspects2010").edits
    by_val = {}
    for n_, v in enumerate(s.sdrr_total):
        if v == v:
            by_val.setdefault(str(int(v)), []).append(n_)
    touch = touching(lines)
    nbk = km_neighbours(s)
    pos = {k: n_ for n_, k in enumerate(s.index)}
    ex = lab[(lab.line >= 0) & lab.exact]
    lines_of = ex.groupby("label").line.agg(set).to_dict()
    vals = np.array([str(int(v)) if v == v else "" for v in s.sdrr_total])
    xs, ys = s.x.values, s.y.values
    out = cost.copy()
    n_ex = n_near = n_far = n_nb = 0
    for r in lab[lab.line >= 0].itertuples():
        if r.exact:
            hit = False
            for i in by_val.get(r.label, []):
                if xs[i] == xs[i] and np.hypot(xs[i] - r.x, ys[i] - r.y) > far_km * 1000:
                    nb_lines = set().union(*[lines_of.get(vals[pos[k]], set())
                                             for k in nbk[s.index[i]]]) if nbk[s.index[i]] else set()
                    # a unique 5-digit value on a line of the right length is no misread: the
                    # point is wrong (2025 chainage shifted, e.g. DK11 at Ostrów Wlkp.)
                    sure = (len(r.label) >= 5 and len(by_val[r.label]) == 1 and
                            abs(np.log(max(lines[r.line].length / 1000, 0.1)
                                       / s.dlugosc_km.values[i])) <= np.log(1.5))
                    if not sure and not (nb_lines & (touch[r.line] | {r.line})):
                        continue
                    n_nb += 1
                out[i, r.line] -= exact_bonus
                hit = True
            n_ex += hit
            n_far += not hit
            if hit and len(by_val[r.label]) == 1:
                other = np.array([edits(v, r.label) > 1 if v else True for v in vals])
                out[other, r.line] += reserve
        else:
            near = [v for v in by_val if len(v) == len(r.label) and
                    sum(a_ != b_ for a_, b_ in zip(v, r.label)) == 1]
            for v in near:
                for i in by_val[v]:
                    out[i, r.line] -= near_bonus
            n_near += bool(near)
    print(f"label bonus: exact SDR on a line {n_ex} (of which far from the point but next to a "
          f"km-neighbour's label: {n_nb}; far, ignored: {n_far}), one digit off {n_near}")
    return out


def touching(lines, touch_m=TOUCH_M):
    ends = np.array([c for ln in lines for c in (ln.coords[0][:2], ln.coords[-1][:2])])
    touch = [set() for _ in lines]
    for a_, b_ in cKDTree(ends).query_pairs(touch_m):
        i, j = a_ // 2, b_ // 2
        if i != j:
            touch[i].add(j)
            touch[j].add(i)
    return touch


def km_neighbours(s):
    """Sections whose km ranges meet (within 1 km) on one road. A road and its expressway
    share the chainage (DK7 Tarczyn–Grójec → S7 Grójec bypass, DK8 Marki → S8 Radzymin), so
    'S7' and '7' count as one road; a same-system match is preferred. ('A' is not stripped:
    A2 and DK2 have separate chainages.)"""
    key = s.system.astype(str).str.replace(r"^S(?=\d)", "", regex=True)
    nb = {i: [] for i in s.index}
    for _, g in s.groupby(key):
        g = g.dropna(subset=["pik_pocz", "pik_konc"])
        for a_ in g.index:
            cand = g[(g.index != a_) & ((g.pik_pocz - g.pik_konc[a_]).abs() <= 1.0)]
            if not len(cand):
                continue
            same = cand[cand.system == s.system[a_]]
            b_ = (same if len(same) else cand).pik_pocz.sub(g.pik_konc[a_]).abs().idxmin()
            if b_ not in nb[a_]:
                nb[a_].append(b_)
                nb[b_].append(a_)
    return nb


def repair(s, lines, L, lab, max_len_ratio=2.5):
    """Sections left off the map whose km-neighbour is on the map: take an empty line touching
    the neighbour's line, if its length fits and no label on it reads as another value. A label
    within one edit of the section's value (a digit missed) makes the choice. Repeats, so a
    chain of such sections fills in from its placed end."""
    import importlib
    edits = importlib.import_module("08_suspects2010").edits
    touch = touching(lines)
    nb = km_neighbours(s)
    reads = lab[lab.line >= 0].groupby("line").agg(list)
    n_fix = n_move = 0

    def confirmed(i, j):
        v = str(int(s.sdrr_total[i]))
        return j in reads.index and any(edits(t, v) <= 1 for t in reads.loc[j].label)

    changed, rounds = True, 0
    while changed and rounds < 10:
        changed, rounds = False, rounds + 1
        used = set(s.line[s.line >= 0])
        # stranded: a placed section whose line touches none of its placed km-neighbours'
        # lines and no label confirms it (a namesake-village point put it far away). It moves
        # to an empty line next to a neighbour if one fits its length about as well; the
        # line it leaves can then take a section that was left off.
        stranded = []
        for i in s.index[(s.line >= 0) & s.sdrr_total.notna()]:
            placed = [s.line[k] for k in nb[i] if s.line[k] >= 0]
            j0 = s.line[i]
            if placed and not any(j0 == l or j0 in touch[l] for l in placed) \
                    and not confirmed(i, j0):
                stranded.append(i)
        for i in s.index[(s.line < 0) & s.sdrr_total.notna()].tolist() + stranded:
            v = str(int(s.sdrr_total[i]))
            placed = [s.line[k] for k in nb[i] if s.line[k] >= 0]
            j0 = s.line[i]
            r0 = abs(np.log(max(L[j0], 0.1) / s.dlugosc_km[i])) if j0 >= 0 else np.inf
            best = None
            for j in set().union(*[touch[l] for l in placed]) if placed else ():
                if j in used:
                    continue
                r = abs(np.log(max(L[j], 0.1) / s.dlugosc_km[i]))
                if r > np.log(max_len_ratio) or r > r0 + np.log(1.25):
                    continue
                score = r - 0.5 * sum(j in touch[l] for l in placed)
                if j in reads.index:
                    rd = reads.loc[j]
                    if any(edits(t, v) <= 1 for t in rd.label):
                        score -= 5
                    elif any(e and t != v for t, e in zip(rd.label, rd.exact)):
                        continue
                if best is None or score < best[0]:
                    best = (score, j)
            if best:
                if j0 >= 0:
                    used.discard(j0)
                    n_move += 1
                    print(f"  moved {s.numer_odcinka[i]} {s.nazwa_odcinka[i]}: line {j0} → {best[1]}")
                else:
                    n_fix += 1
                s.loc[i, "line"] = best[1]
                used.add(best[1])
                changed = True
    print(f"repair: {n_fix} sections placed on empty lines next to their km-neighbours, "
          f"{n_move} stranded sections moved there")
    return s


def name_places(names, kinds):
    """OSM places by upper-case name; a name ending in '.' (TOMASZÓW MAZ.) matches by prefix."""
    places = gpd.read_file(config.OSM_GPKG, layer="places")
    places = places[places.place.isin(kinds)]
    keys = places.name.str.upper().values
    geo = list(places.geometry)
    out = {}
    for n in names:
        if n.endswith("."):
            out[n] = [g for k, g in zip(keys, geo) if k.startswith(n[:-1])]
        else:
            out[n] = [g for k, g in zip(keys, geo) if k == n]
    return out


def name_parts(name):
    import re
    return [p.strip() for p in re.split(r"[-/]|OBWODNICA|PRZEJŚCIE|W\. |\d",
                                        str(name)) if len(p.strip()) > 2]


def leftover(s, lines, L, lab, max_ratio=1.35, place_km=8.0, far_km=25.0, again=True):
    """Sections still off the map (no usable counting point, no placed km-neighbour: town
    bypasses, short links). (1) Pair them with empty lines when the length fits and the line
    carries a label within one edit of the value or passes within place_km of a place named in
    the section's name. (2) Swap: an off-map section takes a line held by another section when
    the line is within place_km of a town named in its name, every town/city named in the
    holder's name is > far_km away and no label confirms the holder (a namesake-village point
    put it there: PIASKI /OBWODNICA/ on the Tomaszów Maz. bypass)."""
    import importlib
    edits = importlib.import_module("08_suspects2010").edits
    reads = lab[lab.line >= 0].groupby("line").label.agg(list)
    parts = {i: name_parts(s.nazwa_odcinka[i]) for i in s.index}
    allp = sorted({p for v in parts.values() for p in v})
    anyp = name_places(allp, ["city", "town", "village"])
    towns = name_places(allp, ["city", "town"])

    def dist(i, j, src):
        return min((lines[j].distance(g) / 1000 for p in parts[i] for g in src.get(p, [])),
                   default=np.inf)

    def ok_len(i, j):
        return abs(np.log(max(L[j], 0.1) / s.dlugosc_km[i])) <= np.log(max_ratio)

    def confirmed(i, j):
        v = str(int(s.sdrr_total[i]))
        return j in reads.index and any(edits(t, v) <= 1 for t in reads[j])

    off = s.index[(s.line < 0) & s.sdrr_total.notna()]
    empty = sorted(set(range(len(lines))) - set(s.line[s.line >= 0]))
    pairs = []
    for i in off:
        for j in empty:
            if not ok_len(i, j):
                continue
            lab_ok = confirmed(i, j)
            d = dist(i, j, anyp)
            if not lab_ok and d > place_km:
                continue
            r = abs(np.log(max(L[j], 0.1) / s.dlugosc_km[i]))
            pairs.append((r + min(d, place_km) / place_km - 2 * lab_ok, i, j))
    n_fix = 0
    used_i, used_j = set(), set()
    for c, i, j in sorted(pairs):
        if i in used_i or j in used_j:
            continue
        s.loc[i, "line"] = j
        used_i.add(i)
        used_j.add(j)
        n_fix += 1
        print(f"  leftover {s.numer_odcinka[i]} {s.nazwa_odcinka[i]} → line {j} ({L[j]:.1f} km)")
    n_swap = 0
    holder = {j: i for i, j in zip(s.index, s.line) if j >= 0}
    for i in s.index[(s.line < 0) & s.sdrr_total.notna()]:
        if not any(towns.get(p) for p in parts[i]):
            continue
        for j, h in list(holder.items()):
            if not ok_len(i, j) or dist(i, j, towns) > place_km or confirmed(h, j):
                continue
            if not any(towns.get(p) for p in parts[h]) or dist(h, j, towns) <= far_km:
                continue
            print(f"  swap: {s.numer_odcinka[i]} {s.nazwa_odcinka[i]} takes line {j} from "
                  f"{s.numer_odcinka[h]} {s.nazwa_odcinka[h]} (its towns {dist(h, j, towns):.0f} km away)")
            s.loc[i, "line"], s.loc[h, "line"] = j, -1
            holder[j] = i
            n_swap += 1
            break
    print(f"leftover: {n_fix} sections placed on empty lines by length + label / place name, "
          f"{n_swap} swapped onto lines held by a section named after far towns")
    if n_swap and again:   # the sections swapped out may fit an empty line (Piaski bypass)
        return leftover(s, lines, L, lab, max_ratio, place_km, far_km, again=False)
    return s


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
    d = load_pdf()
    keep = [not off_main(a) for a in d["raw"]]
    raw = [a for a, k in zip(d["raw"], keep) if k]
    bw = d["bw"][np.array(keep)]
    glyph = [a for a in d["glyph"] if not off_main(a)]
    A = d["A"]
    print(f"left out (inset edge, legend): {keep.count(False)} lines, "
          f"{len(d['glyph']) - len(glyph)} glyph pieces")
    lines = [LineString(np.c_[g, np.ones(len(g))] @ A.T) for g in raw]
    L = np.array([ln.length / 1000 for ln in lines])
    bw = np.where(np.isnan(bw), np.nanmedian(bw), bw)
    print(f"2010 map lines: {len(lines)} ({L.sum():,.0f} km); band width median {np.median(bw):.1f} pt")

    s = pd.read_csv(config.SECTIONS_CSV)
    s["dlugosc_km"] = s["dlugosc_km"].fillna(s["pik_konc"] - s["pik_pocz"]).fillna(1.0).clip(lower=0.1)
    lab = read_map_labels(s, raw, glyph, A)
    s = fix_points(s, lab)
    s = neighbour_points(s)
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
    cost = label_bonus(s, lab, lines, cost)
    cost = chain_bonus(s, lines, cost)
    # a section may stay off the map (cost UNASSIGNED) rather than fill a far line, and a
    # line may stay empty: drawn as a road without a count
    rows, cols = linear_sum_assignment(np.c_[cost, np.full((n, n), UNASSIGNED)])
    ok = cols < m
    off = s.loc[rows[~ok], ["numer_odcinka", "nr_drogi", "nazwa_odcinka", "located_by"]]
    rows, cols = rows[ok], cols[ok]
    print(f"left off the map: {len(off)} sections")
    if len(off):
        print(off.to_string())
    s["line"] = -1
    s.loc[rows, "line"] = cols
    s["match_cost"] = np.nan
    s.loc[rows, "match_cost"] = cost[rows, cols]
    s["sdr_band"] = np.nan
    s.loc[rows, "sdr_band"] = sdr_est[cols].round()
    r = np.corrcoef(np.log(s.sdrr_total[rows]), np.log(sdr_est[cols]))[0, 1]
    print(f"assigned {len(rows)} sections; log-SDR vs band-width correlation {r:.2f}")
    s = repair(s, lines, L, lab)
    s = leftover(s, lines, L, lab)
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
                        "placement", "qa_flags", "match_cost", "sdr_band", "line", "located_by",
                        "geometry"] if c in g.columns]
    config.NETWORK_GPKG.unlink(missing_ok=True)
    g[keep].to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    empty = sorted(set(range(m)) - set(s.line[s.line >= 0]))
    gpd.GeoDataFrame({"line": empty}, geometry=[lines[j] for j in empty], crs=2180).to_file(
        config.NETWORK_GPKG, layer="skdr_unmeasured", driver="GPKG")
    print(f"map lines with no section (drawn as roads without a count): {len(empty)}")
    # debug layers: every map line with its label read(s) and the section it got
    gpd.GeoDataFrame(lab.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(lab.x, lab.y),
                     crs=2180).to_file(
        config.NETWORK_GPKG, layer="map_labels", driver="GPKG")
    per = lab[lab.line >= 0].groupby("line").agg(
        labels=("label", lambda v: ";".join(v)),
        label_exact=("exact", "any"))
    ml = gpd.GeoDataFrame({"line": range(len(lines)), "km": L.round(2), "band_pt": np.round(bw, 1),
                           "sdr_band": sdr_est.round()}, geometry=lines, crs=2180)
    ml = ml.join(per, on="line")
    ml = ml.merge(s.loc[s.line >= 0, ["line", "numer_odcinka", "system", "pik_pocz", "sdrr_total"]],
                  on="line", how="left")
    ml.to_file(config.NETWORK_GPKG, layer="map_lines", driver="GPKG")
    print(f"saved {config.NETWORK_GPKG}")


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010")
    main()
