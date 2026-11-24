"""
pdf_labels2010.py — read the SDR value labels printed on GDDKiA's 2010 map (Mapa_SDR2010.pdf).

The labels are drawn as glyph outlines (no text layer); a digit with a hole is several
fragments. Fragments → glyphs (overlapping points), glyphs → labels (3–6 glyphs in a row),
each label rotated upright and every glyph rasterized to 24×24 px, then classified by its
nearest template. Templates are bootstrapped from the map itself: k-means on all glyphs,
clean clusters named by eye once (TEMPLATE_CLUSTERS), 1 vs 4 split by ink. Each label is
read both ways (it may be upside down) and the reading that is an SDR value of the 2010 table
wins. Returns [(page_x, page_y, text, exact)], exact = text is a value in the table.
"""
import numpy as np
import pdfplumber
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

R = 24
MAIN_X = 1150


def _components(pairs, n):
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(g, directed=False)[1]


def glyph_labels(pdf_path):
    pieces = []
    with pdfplumber.open(pdf_path) as pdf:
        for o in pdf.pages[0].curves:
            col = o.get("non_stroking_color")
            if not o.get("fill") or not col or tuple(round(c, 3) for c in col) != (0, 0, 0):
                continue
            a = np.array(o["pts"], float)
            if a[:, 0].min() >= MAIN_X and max(np.ptp(a, 0)) <= 9:
                pieces.append(a)
    allpts = np.vstack(pieces)
    owner = np.repeat(np.arange(len(pieces)), [len(a) for a in pieces])
    pr = cKDTree(allpts).query_pairs(0.35, output_type="ndarray")
    pp = np.unique(np.c_[owner[pr[:, 0]], owner[pr[:, 1]]], axis=0)
    gid = _components(pp[pp[:, 0] != pp[:, 1]], len(pieces))
    glyphs = {}
    for i, k in enumerate(gid):
        glyphs.setdefault(k, []).append(i)
    glyphs = [v for v in glyphs.values()]
    gpts = [np.vstack([pieces[i] for i in v]) for v in glyphs]
    keep = [2.0 < max(np.ptp(a, 0)) < 7.5 for a in gpts]
    glyphs = [v for v, k in zip(glyphs, keep) if k]
    gpts = [a for a, k in zip(gpts, keep) if k]
    gc = np.array([a.mean(0) for a in gpts])
    lid = _components(cKDTree(gc).query_pairs(4.2, output_type="ndarray"), len(gc))
    labels = {}
    for i, k in enumerate(lid):
        labels.setdefault(k, []).append(i)
    out = []
    for v in labels.values():
        if not 3 <= len(v) <= 6:
            continue
        c = gc[v]
        ctr = c.mean(0)
        u = np.linalg.svd(c - ctr)[2][0]
        if u[0] < -1e-6 or (abs(u[0]) < 1e-6 and u[1] > 0):
            u = -u
        nrm = np.array([u[1], -u[0]])
        order = np.argsort((c - ctr) @ u)
        loc_all = np.vstack([np.c_[(gpts[v[k]] - ctr) @ u, (gpts[v[k]] - ctr) @ nrm] for k in order])
        h = np.ptp(loc_all[:, 1]) or 1
        ym = loc_all[:, 1].mean()
        ims = []
        for k in order:
            gi = v[k]
            x0 = ((gpts[gi] - ctr) @ u).mean()
            img = Image.new("L", (R, R), 0)
            dr = ImageDraw.Draw(img)
            for pi in glyphs[gi]:
                a = pieces[pi] - ctr
                q = [((x - x0) / h * R * 0.9 + R / 2, R / 2 - (y - ym) / h * R * 0.9)
                     for x, y in np.c_[a @ u, a @ nrm]]
                if len(q) >= 3:
                    dr.polygon(q, fill=255)
            ims.append(np.array(img, np.float32) / 255)
        out.append((ctr, ims))
    return out


def _blur(M):
    return np.array([gaussian_filter(m.reshape(R, R), 1).ravel() for m in M])


def build_templates(X, k=16, seed=0):
    """k-means on glyph rasters; returns (exemplars, digit labels). Cluster → digit is fixed by
    looking at the cluster montage once; clusters 1 and 4 are told apart by ink."""
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False)]
    for _ in range(40):
        a = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
        C = np.array([X[a == j].mean(0) if (a == j).any() else C[j] for j in range(k)])
    return C, a


def read_labels(pdf_path, table_values, clean, onefour):
    labels = glyph_labels(pdf_path)
    X = np.array([im.ravel() for _, ims in labels for im in ims])
    C, a = build_templates(X)
    ex, lab = [], []
    for c, dg in clean.items():
        idx = np.flatnonzero(a == c)
        d = ((X[idx] - C[c]) ** 2).sum(1)
        idx = idx[np.argsort(d)[:max(10, len(idx) // 2)]]
        ex.append(X[idx]); lab += [dg] * len(idx)
    idx = np.flatnonzero(a == onefour)
    ink = X[idx].sum(1)
    one, four = idx[ink < np.percentile(ink, 60)], idx[ink > np.percentile(ink, 92)]
    ex += [X[one], X[four]]; lab += ["1"] * len(one) + ["4"] * len(four)
    Eb, lab = _blur(np.vstack(ex)), np.array(lab)

    def classify(ims):
        M = _blur(np.array([im.ravel() for im in ims]))
        d = ((M[:, None, :] - Eb[None]) ** 2).sum(-1)
        return "".join(lab[d.argmin(1)]), d.min(1).sum()

    out = []
    for ctr, ims in labels:
        A, sa = classify(ims)
        B, sb = classify([np.rot90(im, 2) for im in ims[::-1]])
        ina, inb = A in table_values, B in table_values
        if ina != inb:
            txt, exact = (A, True) if ina else (B, True)
        else:
            txt, exact = (A if sa <= sb else B), ina
        out.append((ctr[0], ctr[1], txt, exact))
    return out
