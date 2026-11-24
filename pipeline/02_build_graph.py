"""
02_build_graph.py — turn BDOT10k national-road line features into a routable graph.

  * KAT_ISTNIE == 'eksploatowany' features are routable; 'w budowie' ones get oper=False and are
    used only as a costly fallback (config.COST_NOT_OPERATIONAL): BDOT marks bits of roads
    GPR counted in 2025 as under construction (viaducts, rebuilt carriageways)
  * nodes = line endpoints rounded to NODE_ROUND_M, then nodes closer than HEAL_M are
    merged and dangling ends are joined to the nearest node within DANGLE_M
    (the 16 voivodeship sheets of BDOT10k do not always share exact vertices)
  * every edge remembers its road numbers (tokens) so routing can prefer the right road

Reads : config.SKDR_GPKG
Writes: output/skdr_graph.pkl  {graph, edge geometries, node coords, SKDR frames}
"""
import pickle

import geopandas as gpd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString

import config
from common import skdr_tokens

HEAL_M = 3.0
DANGLE_M = 20.0


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

    for i, (geom, tok, op) in enumerate(zip(routable.geometry, routable["tokens"],
                                            routable["oper"])):
        add_edge(int(node_of_end[i, 0]), int(node_of_end[i, 1]), geom, tok, bool(op))

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
    comps = sorted((len(c) for c in nx.connected_components(G)), reverse=True)
    print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges, "
          f"{joined} dangling ends joined, {len(comps)} components (largest {comps[0]:,} nodes)")
    lens = np.array([g.length for g in geoms])
    print(f"edge length median {np.median(lens):.0f} m, p90 {np.percentile(lens, 90):.0f} m")

    with open(config.GRAPH_PKL, "wb") as f:
        pickle.dump({"G": G, "geoms": geoms, "node_xy": node_xy,
                     "skdr_oper": skdr[oper].drop(columns=["tokens", "oper"]),
                     "skdr_other": skdr[~oper].drop(columns=["tokens", "oper"])}, f)
    print(f"saved {config.GRAPH_PKL}")


if __name__ == "__main__":
    main()
