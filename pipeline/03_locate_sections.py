"""
03_locate_sections.py — place every GPR section on the road network by its chainage.

Section-first linear referencing (replaces the old "cut the network, then nearest point"):

  1. Each chainage system (S7, S7j, 94g …) is split into RUNS of contiguous km.
  2. Counting points are ANCHORS: known km (pik_prawy/lewy) + known position.
  3. Between consecutive anchors the route is the cheapest path on the SKDR graph,
     preferring edges of the same road. km → metres is interpolated piecewise-linearly
     between anchors, so the GDDKiA/BDOT length mismatch is absorbed locally.
  4. Before the first / after the last anchor, the run is extended along the graph by
     the remaining km, choosing the branch that heads away from the neighbouring anchor.
  5. Each piece [pik_pocz, pik_konc] is cut out of its run line.
  6. Pieces with no usable anchor are placed from coordinates ('loose' anchor), or by
     attaching them to the adjacent piece of the same section (two-system sections).

Every section therefore gets exactly its own stretch: no section can be lost or take
its neighbour's value. Quality flags say how each one was placed.

Reads : output/gpr2025_sections.csv, output/gpr2025_pieces.csv, output/skdr_graph.pkl
Writes: output/traffic_network_2025.gpkg layers
          sections                 one line per GPR section with SDRR + QA columns
          counting_points          GPR counting points
          skdr_unmeasured          operational national roads not covered by any section
          skdr_not_operational     BDOT10k national roads under construction / planned
"""
import math
import pickle
from collections import defaultdict

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, substring
from shapely.strtree import STRtree

import config

D = pickle.load(open(config.GRAPH_PKL, "rb"))
G, GEOMS, XY = D["G"], D["geoms"], D["node_xy"]
TREE = STRtree(GEOMS)
EDGE_NODES = {d["eid"]: (u, v) for u, v, d in G.edges(data=True)}


# ── routing helpers ───────────────────────────────────────────────────────────────

# multiplier for BDOT 'w budowie' edges; main() sets it to 1 for runs made only of roads
# opened in/after 2025 (status opened_after_count / pending_2026): BDOT still shows those
# as under construction, and the old road alongside must not take their place
NONOP = {"mult": config.COST_NOT_OPERATIONAL}


def edge_mult(d, road, number):
    k = 1.0 if d.get("oper", True) else NONOP["mult"]
    if d.get("osm"):
        k *= config.COST_OSM
    if road in d["tok"]:
        return k * config.COST_SAME_ROAD
    if number in d["num"]:
        return k * config.COST_SAME_NUMBER
    return k * config.COST_OTHER_ROAD


def cost_fn(road, number):
    return lambda u, v, d: d["len"] * edge_mult(d, road, number)


def snap(pt, road, number, radius=config.ANCHOR_SNAP_M):
    """Nearest graph node on the preferred road near *pt* → (node, distance) or (None, inf).
    Operational edges first; 'w budowie' edges only if nothing operational is in range
    (they are often disconnected stubs)."""
    node, dist = _snap(pt, road, number, radius, oper=True)
    return (node, dist) if node is not None else _snap(pt, road, number, radius, oper=False)


def _snap(pt, road, number, radius, oper):
    best = (None, math.inf, math.inf)
    for eid in TREE.query(pt.buffer(radius)):
        if eid not in EDGE_NODES:
            continue
        u, v = EDGE_NODES[eid]
        # OSM patch edges count as fallback (snapped to only when nothing else is near)
        if (G[u][v].get("oper", True) and not G[u][v].get("osm", False)) != oper:
            continue
        g = GEOMS[eid]
        dist = g.distance(pt)
        if dist > radius:
            continue
        score = dist * edge_mult(G[u][v], road, number) + 1e-6
        if score < best[2]:
            f = g.project(pt)
            start = g.coords[0]
            near_u = (math.dist(start, XY[u]) < math.dist(start, XY[v])) == (f < g.length / 2)
            best = (u if near_u else v, dist, score)
    return best[0], best[1]


def oriented(u, v):
    c = list(GEOMS[G[u][v]["eid"]].coords)
    return c if math.dist(c[0], XY[u]) <= math.dist(c[-1], XY[u]) else c[::-1]


def path_coords(nodes):
    coords = [XY[nodes[0]]]
    for u, v in zip(nodes[:-1], nodes[1:]):
        coords.extend(oriented(u, v)[1:])
    return coords


def extend(a, d_target, ref_xy, road, number):
    """Walk *d_target* metres from node *a* along the road, away from *ref_xy*.

    Returns (coords from a outward, flag) with flag in {'ok','clipped','foreign','none'}.
    """
    if d_target < 1:
        return [XY[a]], "ok"
    cost = cost_fn(road, number)
    dist, paths = nx.single_source_dijkstra(G, a, cutoff=d_target * config.COST_OTHER_ROAD + 2000,
                                            weight=cost)
    real = {a: 0.0}
    for v in sorted(dist, key=dist.get):
        if v != a:
            u = paths[v][-2]
            real[v] = real[u] + G[u][v]["len"]
    ax, ay = XY[a]
    if ref_xy is not None:
        dx, dy = ax - ref_xy[0], ay - ref_xy[1]
        n = math.hypot(dx, dy) or 1.0
        dx, dy = dx / n, dy / n

    def away(p):
        if ref_xy is None:
            return math.hypot(p[0] - ax, p[1] - ay)
        return (p[0] - ax) * dx + (p[1] - ay) * dy

    cands = []  # (score, purity, coords)
    for v, p in paths.items():
        if v == a:
            continue
        u = p[-2]
        if real[u] < d_target <= real[v]:
            line = LineString(oriented(u, v))
            pt = line.interpolate(d_target - real[u])
            purity = dist[v] / max(real[v], 1.0)
            cands.append((away(pt.coords[0]), purity, p[:-1], pt.coords[0]))
    pure = [c for c in cands if c[1] <= 1.5]
    if ref_xy is not None:
        # never turn back towards the reference: if the road ends before d_target in the
        # right direction, stop there (clipped) rather than take a full-length wrong way
        pure = [c for c in pure if c[0] > 0]
    if pure:
        best = max(pure, key=lambda c: c[0] / c[1] ** 2)
        return path_coords(best[2]) + [best[3]], "ok"
    # road ends before d_target: stop at the farthest node reached on the right road
    ends = [(away(XY[v]), v) for v in real if v != a and dist[v] / max(real[v], 1) <= 1.5]
    ends = [e for e in ends if e[0] > 0]
    if ends:
        v = max(ends)[1]
        return path_coords(paths[v]), "clipped"
    if cands:
        best = max(cands, key=lambda c: c[0] / c[1] ** 2)
        return path_coords(best[2]) + [best[3]], "foreign"
    return [XY[a]], "none"


_PTS = pd.read_csv(config.SECTIONS_CSV).dropna(subset=["x"])
_PT_TREE = STRtree([Point(x, y) for x, y in zip(_PTS.x, _PTS.y)])
_PT_SEC = _PTS.numer_odcinka.values


def foreign_points(coords, own, radius=60):
    """Counting points of sections other than *own* lying on the line."""
    if len(coords) < 2:
        return 0
    return sum(1 for j in _PT_TREE.query(LineString(coords).buffer(radius))
               if _PT_SEC[j] not in own)


# ── run placement ─────────────────────────────────────────────────────────────────

def place_run(run, anchors, road, number):
    """Place one chainage run. anchors: list of (km, node, kind).

    Consecutive anchors whose connecting path is implausible (missing link in BDOT10k,
    e.g. a through-town stretch managed by the city) split the run into CHAINS; each
    chain is extended to the km midway between it and the next one.
    Returns (geoms, flags): piece index → list of LineStrings / set of QA flags.
    """
    r0, r1 = run["p0"].min(), run["p1"].max()
    dedup = []
    for km, node, kind in sorted(anchors):
        if dedup and (abs(km - dedup[-1][0]) < 0.05 or node == dedup[-1][1]):
            continue
        dedup.append((km, node, kind))
    cost = cost_fn(road, number)

    chains, links = [[dedup[0]]], [[]]
    for a, b in zip(dedup[:-1], dedup[1:]):
        want = max((b[0] - a[0]) * 1000, 1.0)
        try:
            seg = path_coords(nx.dijkstra_path(G, a[1], b[1], weight=cost))
            seg_len = LineString(seg).length if len(seg) > 1 else 0.0
        except nx.NetworkXNoPath:
            seg = None
        if seg is None or seg_len > max(2.0 * want, want + 3000):
            chains.append([b])
            links.append([])
            continue
        chains[-1].append(b)
        links[-1].append((seg, seg_len, seg_len / want))

    geoms, flags = defaultdict(list), defaultdict(set)
    clamp = lambda s: min(max(s, config.SCALE_OK[0]), config.SCALE_OK[1])
    for i, (ch, lk) in enumerate(zip(chains, links)):
        lo = r0 if i == 0 else (chains[i - 1][-1][0] + ch[0][0]) / 2
        hi = r1 if i == len(chains) - 1 else (ch[-1][0] + chains[i + 1][0][0]) / 2
        coords_mid, ctrl_km, ctrl_m = [XY[ch[0][1]]], [ch[0][0]], [0.0]
        bad = []
        for (seg, seg_len, s), (k1, _, _), (k2, _, _) in zip(lk, ch[:-1], ch[1:]):
            if not (config.SCALE_OK[0] <= s <= config.SCALE_OK[1]) and (k2 - k1) > 0.5:
                bad.append((k1, k2))
            coords_mid.extend(seg[1:])
            ctrl_km.append(k2)
            ctrl_m.append(ctrl_m[-1] + seg_len)
        s_first = clamp(lk[0][2]) if lk else 1.0
        s_last = clamp(lk[-1][2]) if lk else 1.0
        d0, d1 = (ch[0][0] - lo) * 1000 * s_first, (hi - ch[-1][0]) * 1000 * s_last
        if len(ch) > 1:
            before, f0 = extend(ch[0][1], d0, XY[ch[1][1]], road, number)
            after, f1 = extend(ch[-1][1], d1, XY[ch[-2][1]], road, number)
        elif len(chains) > 1:
            # lone anchor, but the run has other chains: head away from them (lower km lies
            # away from the next chain, higher km away from the previous one)
            nxt = XY[chains[i + 1][0][1]] if i + 1 < len(chains) else None
            prv = XY[chains[i - 1][-1][1]] if i > 0 else None
            before, f0 = extend(ch[0][1], d0, nxt, road, number)
            after, f1 = extend(ch[-1][1], d1, prv if prv is not None else
                               (before[-1] if len(before) > 1 else None), road, number)
            if nxt is None and len(after) > 1:
                before, f0 = extend(ch[0][1], d0, after[-1], road, number)
        else:
            # one anchor: the direction is not known. Try both (the longer side chosen
            # freely, the other heading away from it, and vice versa) and keep the one that
            # runs over fewer counting points of OTHER sections (S10e at Bydgoszcz went
            # up the S5 instead of along the shared S5/S10)
            own = set(run.numer_odcinka)
            options = []
            for first in ("after", "before"):
                if first == "before":
                    b, fb = extend(ch[0][1], d0, None, road, number)
                    a, fa = extend(ch[-1][1], d1, b[-1] if len(b) > 1 else None, road, number)
                else:
                    a, fa = extend(ch[-1][1], d1, None, road, number)
                    b, fb = extend(ch[0][1], d0, a[-1] if len(a) > 1 else None, road, number)
                options.append((foreign_points(b[::-1] + a[1:], own), b, fb, a, fa))
            _, before, f0, after, f1 = min(options, key=lambda o: o[0])
        coords = before[::-1] + coords_mid[1:] + after[1:]
        if len(coords) < 2:
            continue
        line = LineString(coords)
        len_before = LineString(before).length if len(before) > 1 else 0.0
        km = np.maximum.accumulate(np.array([lo] + ctrl_km + [hi], float))
        m = np.maximum.accumulate(np.array([0.0] + [len_before + x for x in ctrl_m]
                                           + [line.length], float))
        for idx, pc in run.iterrows():
            ka, kb = max(pc.p0, lo), min(pc.p1, hi)
            if kb <= ka:
                continue
            a, b = np.interp([ka, kb], km, m)
            if b - a >= 1:
                geoms[idx].append(substring(line, a, b))
            if any(ka < y and kb > x for x, y in bad):
                flags[idx].add("scale")
            if f0 != "ok" and ka < ch[0][0]:
                flags[idx].add(f0)
            if f1 != "ok" and kb > ch[-1][0]:
                flags[idx].add(f1)
            if len(chains) > 1 and ((i > 0 and ka <= lo + 1e-9) or
                                    (i < len(chains) - 1 and kb >= hi - 1e-9)):
                flags[idx].add("chain_break")
    return geoms, flags


def merge_parts(parts):
    lines = []
    for p in parts:
        lines.extend(p.geoms if p.geom_type == "MultiLineString" else [p])
    if len(lines) == 1:
        return lines[0]
    return linemerge(MultiLineString(lines))


def _ends(geom):
    g = linemerge(geom) if geom.geom_type == "MultiLineString" else geom
    return [c for p in getattr(g, "geoms", [g]) for c in (p.coords[0][:2], p.coords[-1][:2])]


def close_gaps(gout, skdr):
    """Bridge breaks between consecutive sections of one road.

    Where a chainage system ends (S51b → S51c, S7g → S7 …), the run is extended by its
    remaining km, and the GDDKiA and BDOT lengths rarely agree, so the line can stop short
    of the next section. A stretch of the same road that BDOT has open but no section
    covers, running between the loose ends of two different sections, is split at its
    middle and each half is given to the section on its side. Roads through cities that
    GPR does not count are left alone: DK stretches only up to GAP_DK_M and never next to
    a city-limit section; A/S roads (always counted) up to GAP_AS_M."""
    from scipy.spatial import cKDTree
    from common import skdr_tokens
    GAP_AS_M, GAP_DK_M, END_M, STUB_M = 25_000, 2_000, 600, 1_000
    # BDOT road minus what sections cover; cutting (not whole-feature selection) puts the
    # free pieces' ends right at the sections' ends
    bufs = list(gout.geometry.buffer(30, cap_style=2))
    btree = STRtree(bufs)
    free = skdr[["NUMER_DROG", "geometry"]].copy()
    cut = []
    for g in free.geometry:
        hits = btree.query(g, predicate="intersects")
        if len(hits) == 0:
            cut.append(g)
        else:
            from shapely.ops import unary_union
            cut.append(g.difference(unary_union([bufs[j] for j in hits])))
    free["geometry"] = cut
    free = free[~free.geometry.is_empty].explode(index_parts=False)
    free = free[free.geometry.geom_type == "LineString"]
    free["tok"] = free["NUMER_DROG"].map(skdr_tokens)
    ends, owner = [], []
    for i, g in zip(gout.index, gout.geometry):
        for e in _ends(g):
            ends.append(e)
            owner.append(i)
    ends, owner = np.array(ends), np.array(owner)
    tree = cKDTree(ends)
    stree = STRtree(list(gout.geometry))
    sidx = np.array(gout.index)
    add = defaultdict(list)
    n, km = 0, 0.0
    for road in sorted(set(gout.road.dropna())):
        sub = free[free.tok.map(lambda t: road in t)]
        if not len(sub):
            continue
        is_as = road[:1] in "AS"
        u = sub.geometry.unary_union
        merged = linemerge(u) if u.geom_type == "MultiLineString" else u
        for ch in getattr(merged, "geoms", [merged]):
            L = ch.length
            if L < 100 or L > (GAP_AS_M if is_as else GAP_DK_M):
                continue
            # each end of the free stretch must meet a loose end of a section of this road
            # (within END_M: at interchanges the section may end on the other carriageway)
            side = []
            for pt in (ch.coords[0][:2], ch.coords[-1][:2]):
                cand = [(math.dist(pt, ends[k]), k) for k in tree.query_ball_point(pt, END_M)
                        if gout.road[owner[k]] == road]
                side.append(min(cand) if cand else None)
            if None not in side and side[0][1] == side[1][1]:
                side[max(range(2), key=lambda i: side[i][0])] = None  # both ends → one end
            if None in side:
                # A/S stub from a loose section end into an interchange: the other end meets
                # another road's section (S7 link into the S6 at Chwaszczyno …)
                if is_as and L <= STUB_M and side.count(None) == 1:
                    k = next(s for s in side if s is not None)[1]
                    other = Point(ch.coords[-1 if side[0] is not None else 0][:2])
                    if any(gout.geometry[sidx[j]].distance(other) < 60
                           for j in stree.query(other.buffer(60))):
                        add[owner[k]].append(ch)
                        n += 1
                        km += L / 1000
                continue
            (_, ka), (_, kb) = side
            sa, sb = owner[ka], owner[kb]
            # same section is fine only between two of its parts (a break inside it)
            if (sa == sb and ka // 2 == kb // 2) or \
                    math.dist(ends[ka], ends[kb]) < max(300, 0.4 * L):
                continue
            # an end that another section of the road already touches is not loose
            if any(gout.road[sidx[j]] == road and sidx[j] not in (sa, sb)
                   and gout.geometry[sidx[j]].distance(Point(ends[k])) < 60
                   for k in (ka, kb) for j in stree.query(Point(ends[k]).buffer(60))):
                continue
            if not is_as and any("GR. MIASTA" in str(gout.nazwa_odcinka[x]) for x in (sa, sb)):
                continue
            # not a second carriageway running alongside a section of this road
            samples = [ch.interpolate(d) for d in np.arange(50, L, 100)]
            near = sum(1 for p in samples if any(
                gout.road[sidx[j]] == road and gout.geometry[sidx[j]].distance(p) < 80
                for j in stree.query(p.buffer(80))))
            if samples and near / len(samples) > 0.3:
                continue
            add[sa].append(substring(ch, 0, L / 2))
            add[sb].append(substring(ch, L / 2, L))
            n += 1
            km += L / 1000
    for i, extra in add.items():
        gout.at[i, "geometry"] = merge_parts([gout.geometry[i]] + extra)
        fl = [f for f in str(gout.at[i, "qa_flags"] or "").split(",") if f]
        gout.at[i, "qa_flags"] = ",".join(sorted(set(fl) | {"gap_closed"}))
    print(f"gaps closed: {n} ({km:.0f} km) on {len(add)} sections")
    return gout


def _junctions(name):
    """'W. BIELSK PODL. ZACH. - W. BOĆKI' → ['W. BIELSK PODL. ZACH.', 'W. BOĆKI']."""
    parts = [p.split("/")[0].strip().upper() for p in str(name).split(" - ")]
    return parts if len(parts) == 2 else [None, None]


def trim_at_shared_interchanges(gout, near_m=400, min_tail_m=300):
    """Cut a section where it runs past the interchange it is named to end at.

    If section A ends at interchange 'W. X' and a section B of another road starts or ends
    at 'W. X' at a point lying on A's line (not at A's end), A's line beyond that point is
    a run-on onto a road that GPR does not continue on (S19 south of Boćki: built, closed
    in 2025; traffic leaves for DK19). A keeps the side whose length matches its GPR length.
    """
    from shapely.ops import nearest_points  # noqa: F401
    j = gout.nazwa_odcinka.map(_junctions)
    by_name = defaultdict(list)
    for i, (a, b) in j.items():
        for nm in (a, b):
            if nm and nm.startswith("W. "):
                by_name[nm].append(i)
    n = 0
    for i, names in j.items():
        line = gout.geometry[i]
        if line.geom_type != "LineString":
            line = linemerge(line)
            if line.geom_type != "LineString":
                continue
        for nm in names:
            if not nm or not nm.startswith("W. "):
                continue
            for k in by_name[nm]:
                if k == i or gout.road[k] == gout.road[i]:
                    continue
                for e in _ends(gout.geometry[k]):
                    p = Point(e)
                    if line.distance(p) > near_m:
                        continue
                    d = line.project(p)
                    if d < min_tail_m or d > line.length - min_tail_m:
                        continue
                    want = gout.dlugosc_km[i] * 1000
                    a, b = substring(line, 0, d), substring(line, d, line.length)
                    keep = a if abs(a.length - want) <= abs(b.length - want) else b
                    if abs(keep.length - want) >= abs(line.length - want):
                        continue  # cutting would not bring it closer to its GPR length
                    line = keep
                    gout.at[i, "geometry"] = keep
                    fl = [f for f in str(gout.at[i, "qa_flags"] or "").split(",") if f]
                    gout.at[i, "qa_flags"] = ",".join(sorted(set(fl) | {"trimmed"}))
                    n += 1
    print(f"sections trimmed at a shared interchange: {n}")
    return gout


def main():
    sec = pd.read_csv(config.SECTIONS_CSV)
    pcs = pd.read_csv(config.OUT / f"gpr{config.YEAR}_pieces.csv")
    sec_by_id = sec.set_index("numer_odcinka")

    # runs of contiguous chainage per system
    pcs = pcs.sort_values(["system", "p0"]).reset_index(drop=True)
    run_id, prev = [], None
    rid = 0
    for _, r in pcs.iterrows():
        if prev is None or r.system != prev.system or r.p0 - prev.p1 > config.RUN_GAP_KM:
            rid += 1
        run_id.append(rid)
        prev = r
    pcs["run"] = run_id

    placed = {}                      # piece index → geometry
    method = {}                      # piece index → anchor method
    qflags = defaultdict(set)        # piece index → flags
    run_lines = {}                   # runs placed from anchors

    def anchor_list(run, loose):
        out = []
        for idx, pc in run.iterrows():
            s = sec_by_id.loc[pc.numer_odcinka]
            if pd.isna(s.x):
                continue
            if not loose and not pc.anchor:
                continue
            if loose and s.pk_in_section:
                continue
            node, dist = snap(Point(s.x, s.y), pc.road, pc.number)
            if node is None:
                continue
            km = s.pk if not loose else (pc.p0 + pc.p1) / 2
            out.append((km, node, "loose" if loose else "strict"))
        return out

    pending = []
    for rid, run in pcs.groupby("run"):
        road, number = run.road.iloc[0], str(run.number.iloc[0])
        kind = "strict"
        anchors = anchor_list(run, loose=False)
        if not anchors:
            anchors, kind = anchor_list(run, loose=True), "loose"
        if not anchors:
            pending.append(rid)
            continue
        new = sec_by_id.loc[run.numer_odcinka, "status"].isin(
            ["opened_after_count", "pending_2026"]).all()
        NONOP["mult"] = 1.0 if new else config.COST_NOT_OPERATIONAL
        geoms, fl = place_run(run, anchors, road, number)
        NONOP["mult"] = config.COST_NOT_OPERATIONAL
        if not geoms:
            pending.append(rid)
            continue
        run_lines[rid] = True
        for idx, parts in geoms.items():
            placed[idx], method[idx] = merge_parts(parts), kind
            qflags[idx] |= fl[idx]
    print(f"runs: {pcs.run.nunique()}  placed by anchors: {len(run_lines)}  pending: {len(pending)}")

    # attach anchorless runs to the adjacent piece of the same (two-system) section
    for _ in range(3):
        still = []
        for rid in pending:
            run = pcs[pcs.run == rid]
            road, number = run.road.iloc[0], str(run.number.iloc[0])
            r0, r1 = run.p0.min(), run.p1.max()
            done = False
            for idx, pc in run.iterrows():
                sib = pcs[(pcs.numer_odcinka == pc.numer_odcinka) & (pcs.index != idx)]
                for sidx, sp in sib.iterrows():
                    if sidx not in placed:
                        continue
                    g = placed[sidx]
                    gl = g if g.geom_type == "LineString" else linemerge(g)
                    if gl.geom_type != "LineString":
                        continue
                    # piece k follows piece k-1: attach at the shared end
                    if sp.part < pc.part:
                        att, ref = gl.coords[-1], gl.coords[0]
                        forward = pc.p0 == r0
                    else:
                        att, ref = gl.coords[0], gl.coords[-1]
                        forward = pc.p1 != r1
                    node, _ = snap(Point(att), road, number, radius=500)
                    if node is None:
                        continue
                    coords, fl = extend(node, (r1 - r0) * 1000, ref, road, number)
                    if len(coords) < 2:
                        continue
                    line = LineString(coords if forward else coords[::-1])
                    for j, q in run.iterrows():
                        a, b = ((q.p0 - r0) * 1000, (q.p1 - r0) * 1000)
                        geom = substring(line, min(a, line.length), min(b, line.length))
                        if geom.length >= 1:
                            placed[j], method[j] = geom, "attached"
                            if fl != "ok":
                                qflags[j].add(fl)
                    done = True
                    break
                if done:
                    break
            if not done:
                still.append(rid)
        pending = still
    print(f"after attaching: {len(pending)} runs unplaced "
          f"({pcs[pcs.run.isin(pending)].eval('p1-p0').sum():.1f} km)")

    # ── assemble sections ────────────────────────────────────────────────────────
    rows = []
    for sid, grp in pcs.groupby("numer_odcinka"):
        parts = [placed[i] for i in grp.index if i in placed]
        s = sec_by_id.loc[sid]
        if parts:
            geom = merge_parts(parts)
        else:
            geom = None
        meth = sorted({method[i] for i in grp.index if i in method})
        fl = sorted(set().union(*[qflags[i] for i in grp.index]))
        missing = sum(1 for i in grp.index if i not in placed)
        rows.append(dict(numer_odcinka=sid, geometry=geom,
                         placement="+".join(meth) if meth else "unplaced",
                         qa_flags=",".join(fl + (["partial"] if 0 < missing < len(grp) else [])),
                         n_systems=len(grp)))
    geo = pd.DataFrame(rows)
    keep = ["numer_odcinka", "nr_drogi", "system", "road", "road_class", "nr_europejski",
            "nazwa_odcinka", "typ_odcinka", "pik_pocz", "pik_konc", "dlugosc_km", "miejscowosc",
            "status", "sdrr_total", "sdrr_motocykle", "sdrr_sam_osobowe", "sdrr_mikrobusy",
            "sdrr_lekkie_ciezarowe", "sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy",
            "sdrr_ciagniki", "sdrr_heavy", "heavy_share", "nr_woj", "nazwa_rejonu",
            "odcinek_gpr2020", "uwagi"]
    out = sec[keep].merge(geo, on="numer_odcinka", how="left")
    gout = gpd.GeoDataFrame(out[out.geometry.notna()], geometry="geometry", crs=2180)
    gout = close_gaps(gout, D["skdr_oper"])
    gout = trim_at_shared_interchanges(gout)
    gout["geom_km"] = (gout.length / 1000).round(3)
    gout["len_ratio"] = (gout["geom_km"] / gout["dlugosc_km"]).round(3)

    unplaced = out[out.geometry.isna()]
    print(f"sections placed: {len(gout)}/{len(out)}  "
          f"({gout.dlugosc_km.sum():.0f} of {out.dlugosc_km.sum():.0f} km)")
    print("placement:", gout.placement.value_counts().to_dict())
    print("flags:", gout.qa_flags.replace("", "none").value_counts().head(10).to_dict())
    if len(unplaced):
        print("unplaced:\n", unplaced[["numer_odcinka", "nr_drogi", "dlugosc_km",
                                       "nazwa_odcinka", "status"]].to_string())

    # ── network context layers ───────────────────────────────────────────────────
    skdr = D["skdr_oper"]
    covered = gout.geometry.buffer(40)
    mids = gpd.GeoDataFrame(geometry=skdr.geometry.interpolate(0.5, normalized=True), crs=2180)
    hit = gpd.sjoin(mids, gpd.GeoDataFrame(geometry=covered, crs=2180), predicate="within")
    unmeasured = skdr[~skdr.index.isin(hit.index)]
    print(f"operational SKDR not covered by any section: {unmeasured.length.sum() / 1000:.0f} km")

    config.NETWORK_GPKG.unlink(missing_ok=True)
    gout.to_file(config.NETWORK_GPKG, layer="sections", driver="GPKG")
    pts = gpd.read_file(config.POINTS_GPKG, layer="counting_points")
    pts.to_file(config.NETWORK_GPKG, layer="counting_points", driver="GPKG")
    gpd.GeoDataFrame(unmeasured, crs=2180).to_file(config.NETWORK_GPKG, layer="skdr_unmeasured",
                                                   driver="GPKG")
    other = D["skdr_other"]
    if len(other):
        # 'w budowie' pieces a counted section runs over were open in 2025 → not shown dashed
        mids = gpd.GeoDataFrame(geometry=other.geometry.interpolate(0.5, normalized=True), crs=2180)
        hit = gpd.sjoin(mids, gpd.GeoDataFrame(geometry=covered, crs=2180), predicate="within")
        used = other.index.isin(hit.index)
        print(f"'w budowie' BDOT pieces used by counted sections: {used.sum()} "
              f"({other[used].length.sum() / 1000:.0f} km)")
        gpd.GeoDataFrame(other[~used], crs=2180).to_file(
            config.NETWORK_GPKG, layer="skdr_not_operational", driver="GPKG")
    if D.get("osm_patches") is not None and len(D["osm_patches"]):
        # OSM pieces (roads BDOT10k lacks) that some section now runs along
        op = D["osm_patches"]
        mid = gpd.GeoDataFrame(geometry=op.geometry.interpolate(0.5, normalized=True), crs=2180)
        hit = gpd.sjoin(mid, gpd.GeoDataFrame(geometry=covered, crs=2180), predicate="within")
        used = op[op.index.isin(hit.index)]
        print(f"OSM patches used by sections: {len(used)} ({used.length.sum() / 1000:.0f} km)")
        gpd.GeoDataFrame(used, crs=2180).to_file(config.NETWORK_GPKG, layer="osm_patches_used",
                                                 driver="GPKG")
    unplaced.drop(columns="geometry").to_csv(config.OUT / "qa_unplaced_sections.csv", index=False)
    print(f"saved {config.NETWORK_GPKG}")


if __name__ == "__main__":
    main()
