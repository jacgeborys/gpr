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
SUPERSEDED_NEAR_M = 20_000  # old DK N stretch this close to a counted S N section …
SUPERSEDED_FAR_M = 10_000   # … and this far from any counted DK N section is dropped
LOOSE_PAIR_M = 8_000       # two loose section ends this close are joined along the road …
FOLLOW_M = 8_000
HOLE_JUMP_M = 600          # … starting up to this far from the end (BDOT holes)           # a loose end follows its own road this far to reach the network
CITY_GUARD_M = 1_000       # … unless one lies in / at a city with powiat rights
PARALLEL_M = 2_500          # an uncounted chain entirely this close to a counted route duplicates it
STRAIGHT_M = 30
MAX_STRAIGHT_M = 2_000     # no straight joins longer than this (no road between → no join)          # shorter joins are drawn straight

D = pickle.load(open(config.GRAPH_PKL, "rb"))
G, GEOMS, XY = D["G"], D["geoms"], D["node_xy"]
NODES = np.array(list(G.nodes))
NODE_TREE = cKDTree(np.array([XY[n] for n in NODES]))


def road_path(p, q):
    """Coordinates of a road path from p to q (both included); a straight line if there is
    no sensible road path and they are at most MAX_STRAIGHT_M apart; otherwise None."""
    d = math.dist(p, q)
    straight = [p, q] if d <= MAX_STRAIGHT_M else None
    if d < STRAIGHT_M:
        return [p, q]
    _, (i, j) = NODE_TREE.query([p, q])
    u, v = int(NODES[i]), int(NODES[j])
    try:
        nodes = nx.dijkstra_path(G, u, v, weight="len")
    except nx.NetworkXNoPath:
        return straight
    coords = [p]
    for a, b in zip(nodes[:-1], nodes[1:]):
        c = list(GEOMS[G[a][b]["eid"]].coords)
        if math.dist(c[0], XY[a]) > math.dist(c[-1], XY[a]):
            c = c[::-1]
        coords.extend(c)
    coords.append(q)
    line = LineString(coords)
    if line.length > max(3 * d, d + 3000):
        return straight
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
        link = road_path(coords[-1], cc[0]) if at_end else road_path(cc[-1], coords[0])
        if link is None:
            continue   # a stray piece far away with no road to it: dropped
        if at_end:
            coords = coords + link[1:-1] + cc
        else:
            coords = cc + link[1:-1] + coords
    return coords


def junction_names(name):
    parts = [p.split("/")[0].strip().upper() for p in str(name).split(" - ")]
    return parts if len(parts) == 2 else [None, None]


def drop_superseded(unmeasured, sec):
    """Old national-road alignments replaced by an expressway: an uncounted BDOT stretch of
    DK N with a counted S N section within SUPERSEDED_NEAR_M and no counted DK N section within
    SUPERSEDED_FAR_M was downgraded (BDOT lags; e.g. DK61 north of Ostrów Maz. now that S61
    is open, old DK19 Bielsk Podl.–Boćki). Such stretches are dropped from context and model."""
    from common import skdr_tokens
    mids = unmeasured.geometry.interpolate(0.5, normalized=True)
    keep = np.ones(len(unmeasured), bool)
    by_road = {r: g.geometry.unary_union for r, g in sec[sec.counted_road.notna()].groupby("counted_road")}
    for k, (v, p) in enumerate(zip(unmeasured["NUMER_DROG"], mids)):
        if not skdr_tokens(v):
            keep[k] = False   # national road without a number: being handed over / downgraded
            continue
        for tok in skdr_tokens(v):
            if tok[:1] in "AS":
                continue
            s_geom, dk_geom = by_road.get("S" + tok), by_road.get(tok)
            if s_geom is not None and s_geom.distance(p) <= SUPERSEDED_NEAR_M and (
                    dk_geom is None or dk_geom.distance(p) > SUPERSEDED_FAR_M):
                keep[k] = False
    # parallel old alignments: merge what is left into chains; a chain all of whose points lie
    # within PARALLEL_M of a counted section of the same number (DK N / S N / A N), or of a
    # counted A/S road when its own number has no counted section within SUPERSEDED_FAR_M,
    # duplicates a counted route (old road through a town next to its bypass, old DK8 next to
    # S61 north of Suwałki …)
    rest = unmeasured[keep]
    merged = linemerge(rest.geometry.unary_union)
    chains = [c for c in getattr(merged, "geoms", [merged]) if c.geom_type == "LineString"]
    as_geom = sec[sec.counted_road.fillna("").str[:1].isin(["A", "S"])].geometry.unary_union
    ctree = STRtree(list(rest.geometry))
    drop_idx = set()
    rest_tok = rest["NUMER_DROG"].map(skdr_tokens).tolist()
    city = None
    if config.OSM_GPKG.exists():
        try:
            city = gpd.read_file(config.OSM_GPKG, layer="cities").geometry.buffer(
                CITY_GUARD_M).unary_union
        except Exception:
            city = None
    for c in chains:
        if city is not None and city.contains(c.interpolate(0.5, normalized=True)):
            continue   # a city's own through-road (GPR does not count it): keep for routing
        hits = ctree.query(c.buffer(1), predicate="intersects")
        toks = set().union(*[rest_tok[h] for h in hits]) if len(hits) else set()
        nums = {x.lstrip("AS") for x in toks}
        same = [by_road[r] for n in nums for r in (n, "S" + n, "A" + n) if r in by_road]
        pts = [c.interpolate(d) for d in np.linspace(0, c.length, max(3, int(c.length // 250)))]
        def within(geom):
            return all(geom.distance(q) <= PARALLEL_M for q in pts)
        dup = any(within(g) for g in same)
        if not dup and as_geom is not None and not as_geom.is_empty:
            own_far = all(by_road.get(n) is None or by_road[n].distance(c) > SUPERSEDED_FAR_M
                          for n in nums if not n.startswith(("A", "S")))
            dup = own_far and within(as_geom)
        if dup:
            drop_idx.update(rest.index[h] for h in hits)
    keep2 = ~unmeasured.index.isin(drop_idx) & keep
    dropped = unmeasured[~keep2]
    print(f"uncounted old / parallel alignments dropped: {len(dropped)} pieces, "
          f"{dropped.length.sum() / 1000:.0f} km")
    return unmeasured[keep2]


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
            path = road_path(end_xy(ea), end_xy(eb))
            if path is None:
                continue
            first, second, mid = half_split(path)
            extend(ea, first)
            extend(eb, second[::-1])
            new = mid
        elif pa is not None and pb is None:
            link = road_path(end_xy(eb), pa)
            if link is None:
                continue
            extend(eb, link)
            new = pa
        elif pb is not None and pa is None:
            link = road_path(end_xy(ea), pb)
            if link is None:
                continue
            extend(ea, link)
            new = pb
        else:
            if math.dist(pa, pb) > NEAR_M and kind != "consecutive":
                continue   # two established nodes: leave them apart (unless consecutive
                           # sections of one road: then eb runs on to the other node)
            link = road_path(end_xy(eb), pa)
            if link is None:
                continue
            extend(eb, link)
            new = pa
        parent[rb] = ra
        anchor[ra] = new
        counts[kind] += 1

    # ── loose ends: pair two loose ends along the road between them ──────────────────
    # (a section of one road ends where one of another road starts a few km on, the
    # stretch in between has no section: S11h → DK11 near Olesno, DK63 → DK64 at Łomża).
    # Not for ends at a city with powiat rights: GPR leaves the city's own roads out.
    city = None
    if config.OSM_GPKG.exists():
        try:
            city = gpd.read_file(config.OSM_GPKG, layer="cities").geometry.buffer(CITY_GUARD_M).unary_union
        except Exception:
            city = None
    loose = [e for e in all_ends if find(e) == e and e not in anchor
             and (city is None or not city.contains(Point(end_xy(e))))]
    ltree_pts = cKDTree([end_xy(e) for e in loose]) if loose else None
    cand = []
    for a_i, e in enumerate(loose):
        for b_i in ltree_pts.query_ball_point(end_xy(e), LOOSE_PAIR_M):
            if b_i > a_i and loose[b_i] // 2 != e // 2:
                cand.append((math.dist(end_xy(e), end_xy(loose[b_i])), e, loose[b_i]))
    paired = 0
    for d, ea, eb in sorted(cand):
        if find(ea) != ea or find(eb) != eb or ea in anchor or eb in anchor:
            continue
        path = road_path(end_xy(ea), end_xy(eb))
        if path is None or len(path) <= 2 or LineString(path).length > max(1.6 * d, d + 1500):
            continue   # no road between them (straight fallback) or a long detour
        first, second, mid = half_split(path)
        extend(ea, first)
        extend(eb, second[::-1])
        parent[eb] = ea
        anchor[ea] = mid
        paired += 1
    print(f"loose ends paired along roads: {paired}")

    # ── loose ends: follow the section's own road until it meets another section ──────
    # (DK20 ends 4 km short of the S11 at Szczecinek, DK25 3 km short of DK15 …)
    lines = {i: LineString(c) for i, c in coords.items()}
    ltree = STRtree([lines[i] for i in sec.index])
    followed = 0
    import os
    dbg = [tuple(map(float, v.split(","))) for v in os.environ.get("STITCH_DEBUG", "").split(";") if v]
    for e in all_ends:
        for dx, dy in dbg:
            if math.dist(end_xy(e), (dx, dy)) < 800:
                print("DEBUG end", e, sec.numer_odcinka[e // 2], sec.road[e // 2], np.round(end_xy(e)),
                      "root", find(e), "anchored", e in anchor or find(e) in anchor)
        if find(e) != e or e in anchor:
            continue
        i = e // 2
        p = end_xy(e)
        if city is not None and city.contains(Point(p)):
            continue
        road = str(sec.road[i])
        num = road.lstrip("AS")
        on_road = lambda u, v, d: d["len"] if (road in d["tok"] or num in d["num"]) else None
        # start at the nearest node, and also at own-road nodes up to HOLE_JUMP_M away (a hole
        # in BDOT right at the section end: DK25 near Inowrocław, S7 at Grójec)
        starts = [int(NODES[k]) for k in sorted(NODE_TREE.query_ball_point(p, HOLE_JUMP_M),
                                                key=lambda k: math.dist(p, XY[int(NODES[k])]))]
        starts = [n for n in starts if any(road in G[n][m]["tok"] or num in G[n][m]["num"]
                                           for m in G[n])] or [int(NODES[NODE_TREE.query(p)[1]])]
        best, tried = None, set()
        for start in starts[:15]:
            if start in tried:
                continue
            try:
                dist, paths = nx.single_source_dijkstra(G, start, cutoff=FOLLOW_M, weight=on_road)
            except nx.NodeNotFound:
                continue
            tried.update(dist)
            for v in sorted(dist, key=dist.get):
                if dist[v] < 300 and math.dist(p, XY[start]) < 50:
                    continue   # still at the section's own end
                q = Point(XY[v])
                hit = [sec.index[j] for j in ltree.query(q.buffer(40))
                       if sec.index[j] != i and lines[sec.index[j]].distance(q) <= 40]
                if hit:
                    best = v
                    break
            if best is not None:
                break
        if best is None:
            continue
        nodes = paths[best]
        path = [p]
        for a, b in zip(nodes[:-1], nodes[1:]):
            c = list(GEOMS[G[a][b]["eid"]].coords)
            if math.dist(c[0], XY[a]) > math.dist(c[-1], XY[a]):
                c = c[::-1]
            path.extend(tuple(x[:2]) for x in c)
        extend(e, path)
        anchor[e] = path[-1]
        followed += 1
    print(f"loose ends followed along their own road to the network: {followed}")

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
        link = road_path(end_xy(e), (q.x, q.y))
        if link is None:
            continue
        extend(e, link)
        tied += 1

    sec["geometry"] = [LineString(coords[i]) for i in sec.index]
    sec["counted_road"] = sec["road"].where(sec["sdrr_total"].notna() | sec["status"].isin(
        ["pending_2026", "opened_after_count"]))
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
    unmeasured = drop_superseded(unmeasured, sec)
    sec.drop(columns="counted_road").to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    gpd.GeoDataFrame(unmeasured, crs=2180).to_file(config.NETWORK_GPKG, layer="skdr_unmeasured",
                                                   driver="GPKG")
    print("saved stitched sections")


if __name__ == "__main__":
    main()
