"""
03b_stitch_network.py — make the section network continuous.

Step 03 places every section by its own chainage, which leaves breaks wherever BDOT10k
and GDDKiA disagree (renumbered stretches, old vs new alignments, unmapped interchange
cores …). For a flow map and a traffic model, continuity matters more than the exact
alignment inside an interchange, so here section ends are tied together:

  0. a section drawn in several pieces gets its pieces joined;
  1. consecutive sections of one chainage system (A ends at km k, B starts at km k),
     sections of different roads named after the same interchange ('W. BOĆKI'), and any
     section ends closer than NEAR_M are joined: the shortest road path between the two
     ends (BDOT10k + OSM graph) is split at its middle, each half goes to its section, so
     both end at exactly the same point. If no sensible road path exists, a straight line;
  2. a section end still loose but within TIE_M of another section's line is extended
     onto that line (T-junction).

Reads/writes: output/traffic_network_2025.gpkg layer 'sections' (geometry, geom_km,
len_ratio, qa_flags += 'stitched'), and refreshes 'skdr_unmeasured'.
"""
import math
import pickle
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from shapely.strtree import STRtree

import config

CONSECUTIVE_M = 30_000   # consecutive sections of one system are joined up to this far apart
SAME_NAME_M = 5_000      # same-named interchange on different roads
NEAR_M = 350             # any two section ends this close are one node
TIE_M = 1_000            # a loose end this close to another section's line is tied onto it
STRAIGHT_M = 30          # shorter joins are drawn straight

D = pickle.load(open(config.GRAPH_PKL, "rb"))
G, GEOMS, XY = D["G"], D["geoms"], D["node_xy"]
NODES = np.array(list(G.nodes))
NODE_TREE = cKDTree(np.array([XY[n] for n in NODES]))


def road_path(p, q):
    """Coordinates of a road path from p to q (both included), or a straight line."""
    d = math.dist(p, q)
    if d < STRAIGHT_M:
        return [p, q]
    _, (i, j) = NODE_TREE.query([p, q])
    u, v = int(NODES[i]), int(NODES[j])
    try:
        nodes = nx.dijkstra_path(G, u, v, weight="len")
    except nx.NetworkXNoPath:
        return [p, q]
    coords = [p]
    for a, b in zip(nodes[:-1], nodes[1:]):
        c = list(GEOMS[G[a][b]["eid"]].coords)
        if math.dist(c[0], XY[a]) > math.dist(c[-1], XY[a]):
            c = c[::-1]
        coords.extend(c)
    coords.append(q)
    line = LineString(coords)
    if line.length > max(3 * d, d + 3000):
        return [p, q]
    return [tuple(c[:2]) for c in line.coords]


def half_split(coords):
    """Split a polyline at half its length → (first half, second half, midpoint)."""
    line = LineString(coords)
    if line.length == 0:
        return [coords[0]], [coords[0]], coords[0]
    from shapely.ops import substring
    a = substring(line, 0, line.length / 2)
    b = substring(line, line.length / 2, line.length)
    mid = tuple(a.coords[-1][:2])
    return [tuple(c[:2]) for c in a.coords], [tuple(c[:2]) for c in b.coords], mid


def as_single(geom):
    """One LineString: parts merged, remaining breaks joined along roads."""
    if geom.geom_type == "LineString":
        return [tuple(c[:2]) for c in geom.coords]
    merged = linemerge(geom)
    if merged.geom_type == "LineString":
        return [tuple(c[:2]) for c in merged.coords]
    parts = [[tuple(c[:2]) for c in p.coords] for p in merged.geoms]
    parts.sort(key=lambda c: -LineString(c).length)
    coords = parts.pop(0)
    while parts:  # attach the part nearest to either end
        best = None
        for k, c in enumerate(parts):
            for at_end in (True, False):
                tip = coords[-1] if at_end else coords[0]
                for rev in (False, True):
                    cc = c[::-1] if rev else c
                    near = cc[0] if at_end else cc[-1]
                    d = math.dist(tip, near)
                    if best is None or d < best[0]:
                        best = (d, k, at_end, cc)
        _, k, at_end, cc = best
        parts.pop(k)
        if at_end:
            coords = coords + road_path(coords[-1], cc[0])[1:-1] + cc
        else:
            coords = cc + road_path(cc[-1], coords[0])[1:-1] + coords
    return coords


def junction_names(name):
    parts = [p.split("/")[0].strip().upper() for p in str(name).split(" - ")]
    return parts if len(parts) == 2 else [None, None]


def main():
    sec = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    pcs = pd.read_csv(config.OUT / f"gpr{config.YEAR}_pieces.csv")
    coords = {i: as_single(g) for i, g in zip(sec.index, sec.geometry)}
    added = defaultdict(float)

    def end_xy(e):
        i, k = divmod(e, 2)
        return coords[i][-1] if k else coords[i][0]

    def extend(e, path):
        """Path from the end e outward (path[0] == current end)."""
        i, k = divmod(e, 2)
        if len(path) < 2:
            return
        added[i] += LineString(path).length
        if k:
            coords[i] = coords[i] + path[1:]
        else:
            coords[i] = path[::-1][:-1] + coords[i]

    # ── candidate joins ────────────────────────────────────────────────────────────
    idx_of = {sid: i for i, sid in zip(sec.index, sec.numer_odcinka)}
    pairs = []

    def closest_ends(i, j):
        best = min(((math.dist(end_xy(2 * i + a), end_xy(2 * j + b)), 2 * i + a, 2 * j + b)
                    for a in (0, 1) for b in (0, 1)))
        return best

    pcs = pcs[pcs.numer_odcinka.isin(idx_of)].sort_values(["system", "p0"])
    for _, g in pcs.groupby("system"):
        for (_, a), (_, b) in zip(g.iloc[:-1].iterrows(), g.iloc[1:].iterrows()):
            if a.numer_odcinka == b.numer_odcinka or b.p0 - a.p1 > 0.05:
                continue
            d, ea, eb = closest_ends(idx_of[a.numer_odcinka], idx_of[b.numer_odcinka])
            if d <= CONSECUTIVE_M:
                pairs.append((d, ea, eb, "consecutive"))
    names = defaultdict(list)
    for i, nm in zip(sec.index, sec.nazwa_odcinka):
        for n in junction_names(nm):
            if n and n.startswith("W. "):
                names[n].append(i)
    for n, ids in names.items():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                i, j = ids[x], ids[y]
                if sec.road[i] == sec.road[j]:
                    continue
                d, ea, eb = closest_ends(i, j)
                if d <= SAME_NAME_M:
                    pairs.append((d, ea, eb, "same_name"))
    all_ends = list(range(2 * len(sec)))
    tree = cKDTree([end_xy(e) for e in all_ends])
    for ea, eb in tree.query_pairs(NEAR_M):
        if ea // 2 != eb // 2:
            pairs.append((math.dist(end_xy(ea), end_xy(eb)), ea, eb, "near"))

    # ── join, nearest first; each node gets one anchor point ─────────────────────────
    parent = {}

    def find(e):
        parent.setdefault(e, e)
        while parent[e] != e:
            parent[e] = parent[parent[e]]
            e = parent[e]
        return e

    anchor = {}   # root → xy
    counts = defaultdict(int)
    for d, ea, eb, kind in sorted(pairs):
        ra, rb = find(ea), find(eb)
        if ra == rb:
            continue
        pa, pb = anchor.get(ra), anchor.get(rb)
        if pa is None and pb is None:
            first, second, mid = half_split(road_path(end_xy(ea), end_xy(eb)))
            extend(ea, first)
            extend(eb, second[::-1])
            new = mid
        elif pa is not None and pb is None:
            extend(eb, road_path(end_xy(eb), pa))
            new = pa
        elif pb is not None and pa is None:
            extend(ea, road_path(end_xy(ea), pb))
            new = pb
        else:
            if math.dist(pa, pb) > NEAR_M:
                continue   # two established nodes: leave them apart
            extend(eb, road_path(end_xy(eb), pa))
            new = pa
        parent[rb] = ra
        anchor[ra] = new
        counts[kind] += 1

    # ── loose ends: tie onto a nearby section line (T-junction) ──────────────────────
    lines = {i: LineString(c) for i, c in coords.items()}
    ltree = STRtree([lines[i] for i in sec.index])
    tied = 0
    for e in all_ends:
        if find(e) != e or e in anchor:
            continue   # part of a node already
        i = e // 2
        p = Point(end_xy(e))
        best = None
        for j in ltree.query(p.buffer(TIE_M)):
            j = sec.index[j]
            if j == i:
                continue
            d = lines[j].distance(p)
            if d <= TIE_M and (best is None or d < best[0]):
                best = (d, j)
        if best is None or best[0] < 1:
            continue
        q = lines[best[1]].interpolate(lines[best[1]].project(p))
        extend(e, road_path(end_xy(e), (q.x, q.y)))
        tied += 1

    sec["geometry"] = [LineString(coords[i]) for i in sec.index]
    sec["geom_km"] = (sec.length / 1000).round(3)
    sec["len_ratio"] = (sec["geom_km"] / sec["dlugosc_km"]).round(3)
    for i, a in added.items():
        if a > 50:
            fl = [f for f in str(sec.at[i, "qa_flags"] or "").split(",") if f and f != "None"]
            sec.at[i, "qa_flags"] = ",".join(sorted(set(fl) | {"stitched"}))
    print(f"joins: {dict(counts)}; loose ends tied onto a line: {tied}; "
          f"sections extended: {sum(a > 50 for a in added.values())} "
          f"({sum(added.values()) / 1000:.0f} km added)")

    # refresh the uncovered-context layer
    skdr = D["skdr_oper"]
    mids = gpd.GeoDataFrame(geometry=skdr.geometry.interpolate(0.5, normalized=True), crs=2180)
    hit = gpd.sjoin(mids, gpd.GeoDataFrame(geometry=sec.geometry.buffer(40), crs=2180),
                    predicate="within")
    unmeasured = skdr[~skdr.index.isin(hit.index)]
    print(f"operational SKDR not covered by any section: {unmeasured.length.sum() / 1000:.0f} km")
    sec.to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    gpd.GeoDataFrame(unmeasured, crs=2180).to_file(config.NETWORK_GPKG, layer="skdr_unmeasured",
                                                   driver="GPKG")
    print("saved stitched sections")


if __name__ == "__main__":
    main()
