"""
03c_real_shapes2010.py — trace the 2010 map lines onto real road geometry.

Step 03_pdf_sections2010 draws every section on GDDKiA's schematic 2010 map (georeferenced,
median ~80 m but simplified). Here each map line is replaced by the cheapest path through
today's national + regional roads (BDOT10k) between its two ends, where an edge costs its
length × (1 + (distance from the map line / D0_M)²). So the path follows the road the 2010 map
drew: where that road is regional now (a parallel expressway took the number), the regional
road is closer to the 2010 line and wins over the expressway.
A trace is kept only if it stays within MAX_DEV_M of the map line everywhere and its length is
plausible (LEN_RATIO); otherwise the line keeps its PDF shape (column `shape` = 'pdf').

Reads : output/traffic_network_2010.gpkg layers 'sections', 'skdr_unmeasured' (from step 03;
        if 'sections_pdf' exists — a previous run — that is used as the source)
        config.SKDR_GPKG (national roads), config.DW_GPKG (regional roads), skdr_powiatowe.gpkg
        next to it (county roads: tried where the national + regional trace deviates > 250 m
        from the 2010 line — old routes demoted below regional, e.g. old DK17 Lublin–Kurów)
Writes: output/traffic_network_2010.gpkg layers 'sections', 'skdr_unmeasured' (real shapes),
        'sections_pdf', 'unmeasured_pdf' (the map shapes, for QA), 'regional_roads'
"""
import importlib

import fiona
import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge
from shapely.strtree import STRtree

import config

CORRIDOR_M = 3000     # road pieces considered: within this of the map line
D0_M = 400            # distance at which an edge costs twice its length
END_R_M = 1500        # path ends: road nodes within this of the map line's end
END_W = 4.0           # cost per m of getting from the map line's end to the path's end node
MAX_DEV_M = 2500      # accept: every point of the trace within this of the map line …
LEN_RATIO = (0.7, 1.8)  # … and trace length / map-line length within this
GAP_M, GAP_W = 1000, 5.0  # holes in the road data: straight jumps up to GAP_M, cost × GAP_W
POWIAT_GPKG = config.DW_GPKG.parent / "skdr_powiatowe.gpkg"   # county roads (BDOT10k)
POWIAT_W = 1.2        # county roads cost this much more (national / regional preferred) …
RETRY_DEV_M = 250     # … and are tried only when the national + regional trace deviates more
# caches (re-runs of 03 change which section sits on a line, not the lines: traces are reused)
ROADS_CACHE = config.OUT / "roads_cache_2010.pkl"   # road pieces as WKB (fast to load)
TRACE_CACHE = config.OUT / "trace_cache_2010.pkl"   # line + junction nodes → trace
OVERLAP_MAX, OVERLAP_W = 0.25, 4.0   # a trace sharing more of its length with others is
                                    # retraced with the shared pieces costing OVERLAP_W ×
PARAMS = (OVERLAP_MAX, OVERLAP_W, CORRIDOR_M, D0_M, END_R_M, MAX_DEV_M, LEN_RATIO, GAP_M, GAP_W, POWIAT_W, RETRY_DEV_M)


def load_roads():
    """National + regional pieces, then county pieces; cached as WKB (the gpkgs take minutes)."""
    import pickle
    src = [config.SKDR_GPKG, config.DW_GPKG, POWIAT_GPKG]
    stamp = [f.stat().st_mtime if f.exists() else 0 for f in src]
    if ROADS_CACHE.exists():
        with open(ROADS_CACHE, "rb") as f:
            d = pickle.load(f)
        if d["stamp"] == stamp:
            return list(shapely.from_wkb(d["wkb"])), d["n_main"], d["n_nat"], d["n_dw"]
    parts = []
    for f in src:
        if not f.exists():
            parts.append([])
            continue
        g = gpd.read_file(f).to_crs(2180).geometry.explode(index_parts=False)
        parts.append([x for x in g if x is not None and x.geom_type == "LineString"
                      and x.length > 0])
    geoms = parts[0] + parts[1] + parts[2]
    d = dict(stamp=stamp, wkb=shapely.to_wkb(np.asarray(geoms, dtype=object)),
             n_main=len(parts[0]) + len(parts[1]), n_nat=len(parts[0]), n_dw=len(parts[1]))
    with open(ROADS_CACHE, "wb") as f:
        pickle.dump(d, f)
    return geoms, d["n_main"], d["n_nat"], d["n_dw"]


def road_graph():
    geoms, n_main, n_nat, n_dw = load_roads()
    G = nx.Graph()
    key = lambda c: (round(c[0]), round(c[1]))
    for k, g in enumerate(geoms[:n_main]):
        a, b = key(g.coords[0]), key(g.coords[-1])
        if a != b and (not G.has_edge(a, b) or G[a][b]["len"] > g.length):
            G.add_edge(a, b, eid=k, len=g.length)
    # county roads (after n_main): old national routes demoted below regional (old DK17
    # Lublin–Kurów); not in G (junction nodes stay on national / regional roads), only used by
    # the retry trace
    mult = np.ones(len(geoms))
    mult[n_main:] = POWIAT_W
    print(f"road graph: {n_main:,} pieces (national {n_nat:,}, regional {n_dw:,}), "
          f"{G.number_of_nodes():,} nodes; county roads for retries: {len(geoms) - n_main:,}")
    return G, geoms, mult, n_main


def key(c):
    return (round(c[0]), round(c[1]))


def junctions(lines, G, touch_m=600):
    """Ends of map lines that touch (< touch_m) form a junction; each junction gets one road
    node, so the traced lines meeting there share it (no gaps). The node minimises the summed
    distance to the incident map lines; real junctions (degree >= 3) are preferred."""
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse import coo_matrix
    from scipy.spatial import cKDTree
    from shapely.geometry import Point
    E = np.array([c for ln in lines for c in (ln.coords[0][:2], ln.coords[-1][:2])])
    pr = np.array(list(cKDTree(E).query_pairs(touch_m)) or [(0, 0)])
    n = len(E)
    _, lab = connected_components(coo_matrix((np.ones(len(pr)), (pr[:, 0], pr[:, 1])), (n, n)),
                                  directed=False)
    nodes = np.array(list(G.nodes))
    deg = np.array([G.degree(tuple(x)) for x in nodes])
    nt = cKDTree(nodes)
    end_node = [None] * n
    for c in np.unique(lab):
        idx = np.flatnonzero(lab == c)
        cen = E[idx].mean(0)
        cand = nt.query_ball_point(cen, END_R_M)
        if not cand:
            continue
        inc = [lines[i // 2] for i in idx]
        pts = shapely.points(nodes[cand])
        score = sum(shapely.distance(pts, ln) for ln in inc) / len(inc) \
            + 0.3 * np.hypot(*(nodes[cand] - cen).T) - 150 * (deg[cand] >= 3)
        best = tuple(nodes[cand][int(np.argmin(score))])
        for i in idx:
            end_node[i] = best
    print(f"junctions: {len(np.unique(lab))} (from {n} line ends), "
          f"with a road node {sum(e is not None for e in end_node)} ends")
    return end_node


def trace(line, s_node, t_node, G, geoms, tree, mult, avoid=None):
    """Cheapest road path between the two junction nodes, kept near the map line."""
    if s_node is None or t_node is None or s_node == t_node:
        return None
    cand = tree.query(line.buffer(CORRIDOR_M))
    if not len(cand):
        return None
    ga = np.asarray(geoms, dtype=object)[cand]
    lens = shapely.length(ga)
    # mean distance of the piece from the map line (ends + middle)
    d = np.mean([shapely.distance(line, shapely.line_interpolate_point(ga, f, normalized=True))
                 for f in (0, 0.5, 1)], axis=0)
    w = lens * (1 + (d / D0_M) ** 2) * mult[cand]
    if avoid is not None:   # pieces already used by another section's trace cost more
        mid = shapely.line_interpolate_point(ga, 0.5, normalized=True)
        w = np.where(shapely.distance(mid, avoid) < 15, w * OVERLAP_W, w)
    H = nx.Graph()
    for k, wk in zip(cand, w):
        a, b = key(geoms[k].coords[0]), key(geoms[k].coords[-1])
        if a != b and (not H.has_edge(a, b) or H[a][b]["w"] > wk):
            H.add_edge(a, b, w=wk, eid=k)
    if s_node not in H or t_node not in H:
        return None
    # holes in the road data (pieces not joined, or a stretch now a municipal road): a dead
    # end may jump to any node within GAP_M, by a straight piece that costs GAP_W × its length
    from scipy.spatial import cKDTree
    hn = list(H.nodes)
    xy = np.array(hn, float)
    ht = cKDTree(xy)
    for i in [i for i, u in enumerate(hn) if H.degree(u) == 1] + \
             [hn.index(s_node), hn.index(t_node)]:
        for j in ht.query_ball_point(xy[i], GAP_M):
            if j != i and not H.has_edge(hn[i], hn[j]):
                dd = float(np.hypot(*(xy[i] - xy[j])))
                H.add_edge(hn[i], hn[j], w=GAP_W * dd + 50, eid=-1)
    try:
        path = nx.shortest_path(H, s_node, t_node, weight="w")
    except nx.NetworkXNoPath:
        return None
    xy = []
    for u, v in zip(path[:-1], path[1:]):
        e = H[u][v]["eid"]
        c = list(geoms[e].coords) if e >= 0 else [u, v]
        if key(c[0]) != u:
            c = c[::-1]
        xy.extend(c if not xy else c[1:])
    return LineString([p[:2] for p in xy]) if len(xy) > 1 else None


def accept(new, line):
    if new is None:
        return False
    r = new.length / max(line.length, 1)
    if not LEN_RATIO[0] <= r <= LEN_RATIO[1]:
        return False
    return new.hausdorff_distance(line) <= MAX_DEV_M


def deviation(a, b, n=40):
    """Mean distance between two lines (sampled both ways)."""
    f = np.linspace(0, 1, n)
    pa = shapely.line_interpolate_point(a, f, normalized=True)
    pb = shapely.line_interpolate_point(b, f, normalized=True)
    return (shapely.distance(pa, b).mean() + shapely.distance(pb, a).mean()) / 2


def retrace(lines, end_node, G, geoms, trees, mult):
    import pickle
    cache = {}
    if TRACE_CACHE.exists():
        with open(TRACE_CACHE, "rb") as f:
            d = pickle.load(f)
        if d.get("params") == PARAMS:
            cache = d["traces"]
    out, how = [], []
    n_county = n_hit = 0
    for k, line in enumerate(lines):
        s_node, t_node = end_node[2 * k], end_node[2 * k + 1]
        ck = (tuple(np.round(np.asarray(line.coords)[:, :2]).astype(int).ravel()), s_node, t_node)
        best, dev = None, np.inf
        if ck in cache:
            n_hit += 1
            if cache[ck] is not None:
                best = shapely.from_wkb(cache[ck])
        elif line.length >= 300:
            new = trace(line, s_node, t_node, G, geoms, trees[0], mult)
            if accept(new, line):
                best, dev = new, deviation(new, line)
            if dev > RETRY_DEV_M and trees[1] is not None:
                alt = trace(line, s_node, t_node, G, geoms, trees[1], mult)
                if accept(alt, line) and deviation(alt, line) < 0.7 * dev:
                    best, dev = alt, deviation(alt, line)
                    n_county += 1
            cache[ck] = shapely.to_wkb(best) if best is not None else None
        else:
            cache[ck] = None
        if best is not None:
            out.append(best)
            how.append("road")
            continue
        # kept as on the map, but its ends snapped to the junction nodes (no gaps)
        c = [p[:2] for p in line.coords]
        if s_node is not None:
            c[0] = s_node
        if t_node is not None:
            c[-1] = t_node
        out.append(LineString(c) if c[0] != c[-1] else line)
        how.append("pdf")
    # overlap: two sections drawn on one road (Garwolin bypass 2 ran 2 km along Rębków–Garwolin
    # before turning south): retrace the overlapping one, avoiding the other's road
    n_ovl = 0
    road = [i for i, h in enumerate(how) if h == "road"]
    rt = STRtree([out[i] for i in road])
    for a, i in enumerate(road):
        others = [road[b] for b in rt.query(out[i].buffer(15)) if b != a]
        if not others:
            continue
        av = shapely.union_all([out[j] for j in others]).buffer(15)
        if out[i].intersection(av).length / out[i].length <= OVERLAP_MAX:
            continue
        ck = ("ovl", tuple(np.round(np.asarray(lines[i].coords)[:, :2]).astype(int).ravel()),
              end_node[2 * i], end_node[2 * i + 1])
        if ck not in cache:
            alt = None
            for tr in trees:
                if tr is None:
                    continue
                a2 = trace(lines[i], end_node[2 * i], end_node[2 * i + 1], G, geoms, tr, mult,
                           avoid=av)
                if accept(a2, lines[i]) and a2.intersection(av).length / a2.length <= OVERLAP_MAX:
                    alt = a2
                    break
            cache[ck] = shapely.to_wkb(alt) if alt is not None else None
        if cache[ck] is not None:
            out[i] = shapely.from_wkb(cache[ck])
            n_ovl += 1
    print(f"traces retraced off another section's road: {n_ovl}")
    with open(TRACE_CACHE, "wb") as f:
        pickle.dump(dict(params=PARAMS, traces=cache), f)
    print(f"traces from cache: {n_hit} of {len(lines)}; "
          f"new ones retraced with county roads (closer to the 2010 line): {n_county}")
    return out, np.array(how)


def as_line(g):
    if g.geom_type == "LineString":
        return LineString([p[:2] for p in g.coords])
    m = linemerge(g)
    return m if m.geom_type == "LineString" else max(m.geoms, key=lambda q: q.length)


def main():
    layers = fiona.listlayers(config.NETWORK_GPKG)
    src_sec = "sections_pdf" if "sections_pdf" in layers else "sections"
    src_unm = "unmeasured_pdf" if "unmeasured_pdf" in layers else "skdr_unmeasured"
    sec = gpd.read_file(config.NETWORK_GPKG, layer=src_sec)
    unm = gpd.read_file(config.NETWORK_GPKG, layer=src_unm)
    sec.to_file(config.NETWORK_GPKG, layer="sections_pdf", driver="GPKG")
    unm.to_file(config.NETWORK_GPKG, layer="unmeasured_pdf", driver="GPKG")
    G, geoms, mult, n_main = road_graph()
    trees = (STRtree(geoms[:n_main]), STRtree(geoms) if len(geoms) > n_main else None)
    lines = [as_line(g) for g in pd.concat([sec.geometry, unm.geometry])]
    end_node = junctions(lines, G)
    out, how = retrace(lines, end_node, G, geoms, trees, mult)
    n = len(sec)
    new = sec.copy()
    new["geometry"], new["shape"] = out[:n], how[:n]
    new["geom_km"] = (new.length / 1000).round(3)
    un2 = unm.copy()
    un2["geometry"], un2["shape"] = out[n:], how[n:]
    road = how == "road"
    L = np.array([ln.length for ln in lines])
    print(f"traced on roads: {road.sum()} of {len(lines)} lines ({L[road].sum() / L.sum():.0%} "
          f"of length); kept as on the map (ends snapped): {(~road).sum()}")
    new.to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    un2.to_file(config.NETWORK_GPKG, layer="skdr_unmeasured", driver="GPKG")
    # regional roads for the map (pieces along a 2010 national road are dropped)
    importlib.import_module("04_build_network").regional_links(new, un2)
    print(f"saved {config.NETWORK_GPKG.name}: sections, skdr_unmeasured (real shapes), "
          f"sections_pdf, unmeasured_pdf, regional_roads")


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010")
    main()
