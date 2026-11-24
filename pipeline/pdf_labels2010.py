"""
pdf_labels2010.py — read the SDR value labels printed on GDDKiA's 2010 map (Mapa_SDR2010.pdf).

The labels are drawn as glyph outlines (no text layer), each outline split into many small
curve pieces. Steps:
1. pieces → glyphs: pieces whose points touch (0.35 pt) form one glyph;
2. glyphs → clusters: glyphs whose outlines come within GAP_PT of each other (outline gap, not
   centre distance: a narrow '1' sits far from the centre of its neighbour). At junctions a
   cluster holds several labels;
3. every straight run of glyph centres in a cluster is a candidate label: turned upright along
   its axis, a glyph much wider than a digit (two digits printed touching, e.g. '64') cut at
   its thinnest column, each digit rasterized to 24×24 px and classified by nearest
   neighbours in a template bank (data/label_templates2010.npz: digit rasters from the map
   itself, see README), read both ways (a label may be upside down);
4. decoding: the free reading competes with the SDR values of sections whose counting point
   lies near the label (plus values of sections with no located point). A candidate wins when
   it is almost as good as the free reading and clearly better than the other candidates;
5. the longest runs that read as a table value are kept, best first, without sharing glyphs.
Returns [(page_x, page_y, text, exact, how)]; exact = text is a value of the 2010 table,
how = 'free' (read as is) / 'decoded' (nearest candidate) / 'none'.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

R = 24
GAP_PT = 3.5            # outline gap that puts glyphs in one cluster (labels are cut from it)
BANK = Path(__file__).resolve().parent.parent / "data" / "label_templates2010.npz"
NEAR_PT = 110           # candidate values: counting points within this (≈ 30 km)
TAU = 3.0               # decoded: candidate cost − free cost, per glyph (blurred raster units)
MARGIN = 15.0           # decoded: second-best candidate must be this much worse


def _components(pairs, n):
    if len(pairs) == 0:
        return np.arange(n)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _glyphs(pieces):
    allpts = np.vstack(pieces)
    owner = np.repeat(np.arange(len(pieces)), [len(a) for a in pieces])
    pr = cKDTree(allpts).query_pairs(0.35, output_type="ndarray")
    pp = np.unique(np.c_[owner[pr[:, 0]], owner[pr[:, 1]]], axis=0)
    gid = _components(pp[pp[:, 0] != pp[:, 1]], len(pieces))
    G = {}
    for i, k in enumerate(gid):
        G.setdefault(k, []).append(i)
    G = list(G.values())
    gpts = [np.vstack([pieces[i] for i in v]) for v in G]
    keep = [2.0 < max(np.ptp(a, 0)) < 12 for a in gpts]
    return [v for v, k in zip(G, keep) if k], [a for a, k in zip(gpts, keep) if k]


def _dense(a, step=0.3):
    """Outline vertices + points along each edge (a long diagonal stroke has few vertices)."""
    a = np.vstack([a, a[:1]])
    out = [a[:-1]]
    for p, q in zip(a[:-1], a[1:]):
        n = int(np.hypot(*(q - p)) / step)
        if n > 1:
            out.append(p + (q - p) * np.linspace(0, 1, n + 1)[1:-1, None])
    return np.vstack(out)


def _group(gpts, glyphs, pieces):
    """Glyphs → labels by outline gap; sizes must agree (labels are one font size)."""
    dense = [np.vstack([_dense(pieces[i]) for i in g]) for g in glyphs]
    pts = np.vstack(dense)
    owner = np.repeat(np.arange(len(gpts)), [len(a) for a in dense])
    pr = cKDTree(pts).query_pairs(GAP_PT, output_type="ndarray")
    pp = np.unique(np.c_[owner[pr[:, 0]], owner[pr[:, 1]]], axis=0)
    pp = pp[pp[:, 0] != pp[:, 1]]
    lid = _components(pp, len(gpts))
    L = {}
    for i, k in enumerate(lid):
        L.setdefault(k, []).append(i)
    return list(L.values())


def _raster(pieces, glyphs, gi, ctr, u, nrm, x0, h, ym, xr=None):
    img = Image.new("L", (R, R), 0)
    dr = ImageDraw.Draw(img)
    for pi in glyphs[gi]:
        a = pieces[pi] - ctr
        q = [((x - x0) / h * R * 0.9 + R / 2, R / 2 - (y - ym) / h * R * 0.9)
             for x, y in np.c_[a @ u, a @ nrm]]
        if len(q) >= 3:
            dr.polygon(q, fill=255)
    im = np.array(img, np.float32) / 255
    if xr is not None:   # keep only columns of this digit (a split glyph)
        cols = (np.arange(R) - R / 2) / (R * 0.9) * h + x0
        im[:, (cols < xr[0]) | (cols > xr[1])] = 0
    return im


def _cut(pieces, glyphs, gi, ctr, u, nrm, h, ym, lo, hi, n):
    """Split a glyph spanning [lo, hi] along u into n digits at its thinnest columns."""
    xs = np.linspace(lo, hi, 200)
    S = 8.0
    img = Image.new("L", (int((hi - lo) * S) + 3, int(h * 1.6 * S) + 3), 0)
    dr = ImageDraw.Draw(img)
    for pi in glyphs[gi]:
        a = pieces[pi] - ctr
        q = [((x - lo) * S + 1, (ym + h * 0.8 - y) * S + 1) for x, y in np.c_[a @ u, a @ nrm]]
        if len(q) >= 3:
            dr.polygon(q, fill=255)
    ink = np.array(img, float).sum(0)
    cuts = []
    for k in range(1, n):
        c0 = int(len(ink) * (k - 0.35) / n)
        c1 = int(len(ink) * (k + 0.35) / n)
        c = c0 + int(np.argmin(ink[c0:c1 + 1]))
        cuts.append(lo + (c - 1) / S)
    edges = [lo] + cuts + [hi]
    return list(zip(edges[:-1], edges[1:]))


def _chain_ims(pieces, glyphs, gpts, v):
    """Rasters of glyphs v along their common axis, left→right (wide glyphs cut in digits)."""
    allp = np.vstack([gpts[k] for k in v])
    ctr = allp.mean(0)
    c = np.array([gpts[k].mean(0) for k in v])
    u = np.linalg.svd(allp - ctr, full_matrices=False)[2][0]
    if u[0] < -1e-6 or (abs(u[0]) < 1e-6 and u[1] > 0):
        u = -u
    nrm = np.array([u[1], -u[0]])
    loc = [np.c_[(gpts[k] - ctr) @ u, (gpts[k] - ctr) @ nrm] for k in v]
    h = np.median([np.ptp(p[:, 1]) for p in loc]) or 1
    ym = np.median([(p[:, 1].max() + p[:, 1].min()) / 2 for p in loc])
    ims = []
    for k in np.argsort((c - ctr) @ u):
        p = loc[k]
        lo, hi = p[:, 0].min(), p[:, 0].max()
        w = hi - lo
        n = int(round(w / (0.68 * h))) if w > 1.05 * h else 1
        if n <= 1:
            ims.append(_raster(pieces, glyphs, v[k], ctr, u, nrm, p[:, 0].mean(), h, ym))
            continue
        for a, b in _cut(pieces, glyphs, v[k], ctr, u, nrm, h, ym, lo, hi, n):
            ims.append(_raster(pieces, glyphs, v[k], ctr, u, nrm, (a + b) / 2, h, ym, (a, b)))
    return ctr, ims


def _chains(c, step=6.6, lo=2.4, tol=1.6, maxlen=6):
    """All straight runs of glyph centres (start at every pair, extend to the nearest glyph in
    line), plus their contiguous sub-runs of >= 3 glyphs; as sorted index tuples."""
    n = len(c)
    full = set()
    for i in range(n):
        for j in range(n):
            dv = c[j] - c[i]
            L = np.hypot(*dv)
            if i == j or not lo < L <= step:
                continue
            ch = [i, j]
            while len(ch) < maxlen:
                d = c[ch[-1]] - c[ch[0]]
                d = d / np.hypot(*d)
                r = c - c[ch[-1]]
                t, q = r @ d, np.abs(r @ np.array([-d[1], d[0]]))
                ok = [k for k in range(n) if k not in ch and lo < t[k] <= step and q[k] < tol]
                if not ok:
                    break
                ch.append(min(ok, key=lambda k: t[k]))
            full.add(tuple(ch))
    out = set()
    for ch in full:
        for a in range(len(ch)):
            for b in range(a + 3, len(ch) + 1):
                out.add(tuple(sorted(ch[a:b])))
    return out


def _blur(M):
    return np.array([gaussian_filter(m.reshape(R, R), 1).ravel() for m in M])


def _sqdist(A, B):
    return np.maximum((A * A).sum(1)[:, None] + (B * B).sum(1)[None] - 2 * A @ B.T, 0)


def _digit_costs(ims, Eb, lab, k=3):
    """cost[g, d] = mean distance of glyph g to its k nearest exemplars of digit d."""
    M = _blur(np.array([im.ravel() for im in ims]))
    d = _sqdist(M, Eb)
    out = np.empty((len(ims), 10))
    for dg in range(10):
        dd = np.sort(d[:, lab == str(dg)], 1)[:, :k]
        out[:, dg] = dd.mean(1)
    return out


def _read(ims, Eb, lab):
    """Both orientations → [(free text, free cost, cost matrix)]."""
    out = []
    for g in (ims, [np.rot90(im, 2) for im in ims[::-1]]):
        C = _digit_costs(g, Eb, lab)
        out.append(("".join(str(i) for i in C.argmin(1)), C.min(1).sum(), C))
    return out


def _decode(ims, ctr, Eb, lab, table_values, cands):
    """→ (text, how, cost per digit): an exact free reading, else the nearby candidate value
    that is almost as good as the free reading and clearly better than the other candidates."""
    rd = _read(ims, Eb, lab)
    fc = min(r[1] for r in rd)
    for txt, c, _ in sorted(rd, key=lambda r: r[1]):
        if txt in table_values:
            return txt, "free", c / len(ims)
    if cands is not None:
        sc = sorted((C[np.arange(len(v)), [int(ch) for ch in v]].sum() - fc, v)
                    for v in set(cands(*ctr)) for _, _, C in rd if len(v) == len(ims))
        if sc and sc[0][0] <= TAU * len(ims) and                 (len(sc) == 1 or sc[1][0] - sc[0][0] >= MARGIN or sc[1][1] == sc[0][1]):
            return sc[0][1], "decoded", (fc + sc[0][0]) / len(ims)
    best = min(rd, key=lambda r: r[1])
    return best[0], "none", best[1] / len(ims)


def read_labels(pieces, table_values, cands=None, per_digit=250):
    """cands(x, y) → candidate value strings near a page point (optional).
    Each glyph group is segmented by decoding: every straight run of glyphs in it is read, and
    the longest runs that read as a table value (free or decoded) are taken, best first, without
    sharing glyphs. A group with no such run is reported once with its free reading."""
    z = np.load(BANK)
    Eb, lab = _blur(z["X"].astype(np.float32) / 255), z["y"]
    # drop bank exemplars that their own neighbours disagree with (accidental exact reads)
    d = _sqdist(Eb, Eb)
    np.fill_diagonal(d, np.inf)
    nn = np.argsort(d, 1)[:, :5]
    ok = (lab[nn] == lab[:, None]).sum(1) >= 3
    keep = np.concatenate([np.flatnonzero(ok & (lab == str(k)))[:per_digit] for k in range(10)])
    Eb, lab = Eb[keep], lab[keep]
    glyphs, gpts = _glyphs(pieces)
    out = []
    for v in _group(gpts, glyphs, pieces):
        c = np.array([gpts[k].mean(0) for k in v])
        runs = _chains(c)
        if len(v) <= 6:
            runs.add(tuple(range(len(v))))
        found = []
        for ch in runs:
            ctr, ims = _chain_ims(pieces, glyphs, gpts, [v[k] for k in ch])
            if not 3 <= len(ims) <= 6:
                continue
            txt, how, cpd = _decode(ims, ctr, Eb, lab, table_values, cands)
            if how != "none":
                found.append((-len(ims), how != "free", cpd, ch, ctr, txt, how))
        used = set()
        for _, _, _, ch, ctr, txt, how in sorted(found, key=lambda f: f[:3]):
            if used.isdisjoint(ch):
                used |= set(ch)
                out.append((ctr[0], ctr[1], txt, True, how))
        if not used and runs:   # nothing readable: report the longest run as read
            ch = max(runs, key=len)
            ctr, ims = _chain_ims(pieces, glyphs, gpts, [v[k] for k in ch])
            if 3 <= len(ims) <= 6:
                txt, how, _ = _decode(ims, ctr, Eb, lab, table_values, None)
                out.append((ctr[0], ctr[1], txt, False, "none"))
    return out
