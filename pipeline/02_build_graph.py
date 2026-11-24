"""
02_build_graph.py — turn BDOT10k national-road line features into a routable graph.

  * KAT_ISTNIE == 'eksploatowany' features are routable; 'w budowie' ones get oper=False and are
    used only as a costly fallback (config.COST_NOT_OPERATIONAL): BDOT marks bits of roads
    GPR counted in 2025 as under construction (viaducts, rebuilt carriageways)
  * nodes = line endpoints rounded to NODE_ROUND_M, then nodes closer than HEAL_M are
    merged and dangling ends are joined to the nearest node within DANGLE_M
    (the 16 voivodeship sheets of BDOT10k do not always share exact vertices)
  * every edge remembers its road numbers (tokens) so routing can prefer the right road
  * OSM main roads fill what BDOT lacks (osm=True edges, costlier: config.COST_OSM)

Reads : config.SKDR_GPKG, config.OSM_GPKG (optional, from 00b_fetch_osm.py)
Writes: output/skdr_graph.pkl  {graph, edge geometries, node coords, SKDR frames}
"""
import math
import pickle

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString
from shapely.ops import substring

import config
from common import skdr_tokens

HEAL_M = 3.0
DANGLE_M = 20.0
DANGLE_ROAD_M = 200.0
DANGLE_AS_M = 1000.0
DANGLE_TO_AS_M = 600.0
MAX_EDGE_M = 250.0
OSM_BUFFER_M = 40.0   # OSM within this of a BDOT national road = BDOT already has it
OSM_MIN_M = 60.0      # shorter OSM leftovers are carriageway/vertex noise
OSM_TIE_M = 80.0      # an OSM patch end is tied to a BDOT node this close


class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def osm_patches(skdr, G, node_xy, add_edge, next_id):
    """Add OSM motorway/trunk/primary (+ links) pieces that BDOT10k lacks.

    Each OSM way is cut by a OSM_BUFFER_M buffer around every BDOT national road (so
    where BDOT has the road, BDOT is used); what remains, if at least OSM_MIN_M long, is
    added as edges with osm=True (costlier, see config.COST_OSM), and each loose end is
    tied to the nearest graph node within OSM_TIE_M. Returns the patch GeoDataFrame.
    """
    if not config.OSM_GPKG.exists():
        print("no OSM layer (run 00b_fetch_osm.py) — skipping OSM patches")
        return None
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    osm = gpd.read_file(config.OSM_GPKG, layer="roads")
    bufs = list(skdr.geometry.buffer(OSM_BUFFER_M, cap_style=2))
    btree = STRtree(bufs)
    rows = []
    for geom, hw, ref in zip(osm.geometry, osm.highway, osm.ref):
        hits = btree.query(geom, predicate="intersects")
        rest = geom.difference(unary_union([bufs[j] for j in hits])) if len(hits) else geom
        for p in getattr(rest, "geoms", [rest]):
            if p.geom_type == "LineString" and p.length >= OSM_MIN_M:
                rows.append(dict(highway=hw, ref=ref, geometry=p))
    patches = gpd.GeoDataFrame(rows, crs=2180)
    # node ids: patch ends rounded to 1 m (OSM ways meet at shared vertices), then tied
    # to the BDOT graph where they touch it
    bdot_nodes = np.array(list(G.nodes))
    btree_n = cKDTree(np.array([node_xy[n] for n in bdot_nodes]))
    end_id = {}
    tied = 0

    def node_for(xy):
        nonlocal next_id, tied
        key = (round(xy[0]), round(xy[1]))
        if key not in end_id:
            end_id[key] = next_id
            node_xy[next_id] = xy
            next_id += 1
            d, j = btree_n.query(xy, distance_upper_bound=OSM_TIE_M)
            if np.isfinite(d):
                m = int(bdot_nodes[j])
                add_edge(end_id[key], m, LineString([xy, node_xy[m]]), tok, True)
                G[end_id[key]][m]["osm"] = True
                tied += 1
        return end_id[key]

    for geom, ref in zip(patches.geometry, patches.ref):
        tok = skdr_tokens(ref)
        u, v = node_for(geom.coords[0][:2]), node_for(geom.coords[-1][:2])
        k = max(1, int(np.ceil(geom.length / MAX_EDGE_M)))
        cuts = np.linspace(0, geom.length, k + 1)
        chain = [u]
        for d in cuts[1:-1]:
            p = geom.interpolate(d)
            node_xy[next_id] = (p.x, p.y)
            chain.append(next_id)
            next_id += 1
        chain.append(v)
        for a, b, d0, d1 in zip(chain[:-1], chain[1:], cuts[:-1], cuts[1:]):
            if a != b:
                add_edge(a, b, substring(geom, d0, d1), tok, True)
                G[a][b]["osm"] = True
    print(f"OSM patches: {len(patches):,} pieces, {patches.length.sum() / 1000:,.0f} km "
          f"({patches.groupby('highway').geometry.apply(lambda x: round(x.length.sum() / 1000)).to_dict()}), "
          f"{tied} ends tied to BDOT")
    return patches


def main():
    skdr = gpd.read_file(config.SKDR_GPKG, layer="skdr_krajowe").to_crs(2180)
    skdr = skdr.explode(index_parts=False).reset_index(drop=True)
    skdr = skdr[skdr.geometry.geom_type == "LineString"].copy()
    skdr["tokens"] = skdr["NUMER_DROG"].map(skdr_tokens)
    if "KAT_ISTNIE" in skdr.columns:
        oper = skdr["KAT_ISTNIE"].fillna("eksploatowany") == "eksploatowany"
    else:
        oper = np.ones(len(skdr), bool)
    print(f"SKDR features: {len(skdr):,}  operational: {oper.sum():,}  other: {(~oper).sum():,}")
    if (~oper).any():
        print(skdr.loc[~oper, "KAT_ISTNIE"].value_counts().to_string())
    skdr["oper"] = oper
    # operational first, so a parallel duplicate keeps the operational edge
    routable = skdr.sort_values("oper", ascending=False).reset_index(drop=True)

    # --- endpoints → nodes ------------------------------------------------------------
    ends = np.array([[g.coords[0], g.coords[-1]] for g in routable.geometry])  # (n,2,2)
    flat = np.round(ends.reshape(-1, 2) / config.NODE_ROUND_M) * config.NODE_ROUND_M
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    uf = UnionFind(len(uniq))
    for a, b in cKDTree(uniq).query_pairs(HEAL_M):
        uf.union(a, b)
    root = np.array([uf.find(i) for i in range(len(uniq))])
    node_of_end = root[inv].reshape(-1, 2)
    node_xy = {int(r): tuple(uniq[r]) for r in np.unique(root)}

    G = nx.Graph()
    geoms, toks, nums = [], [], []

    def add_edge(u, v, geom, tok, op=True):
        if u == v:
            return
        length = geom.length
        e = G.get_edge_data(u, v)
        if e and ((e["oper"] and not op) or (e["oper"] == op and e["len"] <= length)):
            G[u][v]["tok"] = G[u][v]["tok"] | tok
            G[u][v]["num"] = frozenset(t.lstrip("AS") for t in G[u][v]["tok"])
            return
        eid = len(geoms)
        geoms.append(geom)
        G.add_edge(u, v, eid=eid, len=length, tok=tok, oper=op,
                   num=frozenset(t.lstrip("AS") for t in tok))

    # long features are split into ≤ MAX_EDGE_M edges: anchors snap to graph nodes, so a
    # 7 km feature (whole new expressways come as one) would move an anchor by kilometres
    next_id = len(uniq)
    for i, (geom, tok, op) in enumerate(zip(routable.geometry, routable["tokens"],
                                            routable["oper"])):
        u, v = int(node_of_end[i, 0]), int(node_of_end[i, 1])
        k = int(np.ceil(geom.length / MAX_EDGE_M))
        if k <= 1 or u == v:
            add_edge(u, v, geom, tok, bool(op))
            continue
        cuts = np.linspace(0, geom.length, k + 1)
        chain = [u]
        for d in cuts[1:-1]:
            p = geom.interpolate(d)
            node_xy[next_id] = (p.x, p.y)
            chain.append(next_id)
            next_id += 1
        chain.append(v)
        for a, b, d0, d1 in zip(chain[:-1], chain[1:], cuts[:-1], cuts[1:]):
            add_edge(a, b, substring(geom, d0, d1), tok, bool(op))

    # --- join dangling ends to the nearest other node -------------------------------
    nodes = np.array(list(G.nodes))
    xy = np.array([node_xy[n] for n in nodes])
    tree = cKDTree(xy)
    joined = 0
    for n in [n for n in G.nodes if G.degree(n) == 1]:
        dists, idx = tree.query(node_xy[n], k=4, distance_upper_bound=DANGLE_M)
        for d, j in zip(dists, idx):
            if not np.isfinite(d) or j >= len(nodes):
                continue
            m = int(nodes[j])
            if m == n or m in G[n] or any(m in G[k] for k in G[n]):
                continue
            nb = next(iter(G[n]))
            add_edge(n, m, LineString([node_xy[n], node_xy[m]]), G[n][nb]["tok"], G[n][nb]["oper"])
            joined += 1
            break
    # --- second pass: longer holes, only along the same road -------------------------
    # BDOT10k has occasional 50–200 m holes in a road (e.g. S7 near Elbląg). A dead end
    # is joined to a node of the same road number within DANGLE_ROAD_M, unless the two
    # are already connected by a short path (then it is just a ramp or carriageway end).
    nodes = np.array(list(G.nodes))
    tree = cKDTree(np.array([node_xy[n] for n in nodes]))
    healed = 0
    for n in [n for n in G.nodes if G.degree(n) == 1]:
        nb = next(iter(G[n]))
        tok = G[n][nb]["tok"]
        if not tok:
            continue
        # expressways/motorways: holes up to DANGLE_AS_M (unmapped interchange cores, e.g.
        # S6 at Węzeł Chwaszczyno is missing ~600 m); other roads up to DANGLE_ROAD_M
        as_tok = frozenset(t for t in tok if t[:1] in "AS")
        # a DK dead end may also reach an expressway/motorway interchange within
        # DANGLE_TO_AS_M (DK20 at Węzeł Szczecinek Płd.: the connecting ramps are unmapped)
        radius = DANGLE_AS_M if as_tok else DANGLE_TO_AS_M
        cand = sorted((math.dist(node_xy[n], node_xy[int(nodes[j])]), int(nodes[j]))
                      for j in tree.query_ball_point(node_xy[n], radius))
        near = nx.single_source_dijkstra_path_length(G, n, cutoff=6 * radius, weight="len")
        for d, m in cand:
            if d <= DANGLE_M or m in near:
                continue
            if as_tok or d <= DANGLE_ROAD_M:
                need = as_tok if d > DANGLE_ROAD_M else tok
                ok = any(G[m][k]["tok"] & need for k in G[m])
            else:   # DK end, 200–600 m: only onto an A/S road
                ok = any(any(x[:1] in "AS" for x in G[m][k]["tok"]) for k in G[m])
            if not ok:
                continue
            add_edge(n, m, LineString([node_xy[n], node_xy[m]]), tok, G[n][nb]["oper"])
            healed += 1
            break
    # --- OSM patches: main roads BDOT10k does not have ------------------------------
    patches = osm_patches(skdr, G, node_xy, add_edge, next_id)

    comps = sorted((len(c) for c in nx.connected_components(G)), reverse=True)
    print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges, "
          f"{joined} dangling ends joined, {healed} same-road holes healed (≤{DANGLE_ROAD_M:.0f} m, A/S ≤{DANGLE_AS_M:.0f} m), "
          f"{len(comps)} components (largest {comps[0]:,} nodes)")
    lens = np.array([g.length for g in geoms])
    print(f"edge length median {np.median(lens):.0f} m, p90 {np.percentile(lens, 90):.0f} m")

    with open(config.GRAPH_PKL, "wb") as f:
        pickle.dump({"G": G, "geoms": geoms, "node_xy": node_xy,
                     "skdr_oper": skdr[oper].drop(columns=["tokens", "oper"]),
                     "skdr_other": skdr[~oper].drop(columns=["tokens", "oper"]),
                     "osm_patches": patches}, f)
    print(f"saved {config.GRAPH_PKL}")


if __name__ == "__main__":
    main()
