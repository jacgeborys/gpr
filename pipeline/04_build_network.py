"""
04_build_network.py — node/link topology for traffic modelling.

  1. Ends of all placed GPR sections are clustered (single linkage, NODE_MERGE_M):
     consecutive sections of one road, and roads meeting at a junction, share a node.
  2. T-junctions: where a node lies within TJUNCTION_M of another section's interior
     (a road joins mid-section, which GPR does not always cut at), that section is split
     there into two links carrying the same counts.
  3. Mid-section crossings: two DK roads crossing → connected (at-grade junction);
     a crossing involving an A/S road → connected only if an operational interchange
     (BDOT10k SKRW węzeł) lies within INTERCHANGE_M, otherwise treated as an overpass.

Each link keeps its GPR section id (numer_odcinka), so counts can be used for model
calibration; several links may share one section after T-junction splits.

Reads : output/traffic_network_2025.gpkg  layer 'sections'
Writes: output/traffic_network_2025.gpkg  layers 'nodes', 'links', 'regional_roads'
        output/links_2025.csv, output/nodes_2025.csv
"""
from collections import defaultdict

import geopandas as gpd
import pandas as pd
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, substring
from shapely.strtree import STRtree

import config
from common import road_class, skdr_tokens

NODE_MERGE_M = 350.0   # interchange ramps and dual carriageways sit within this
TJUNCTION_M = 300.0    # a node this close to another section's interior splits it
END_GUARD_M = 150.0    # ...unless the split point is this close to that section's end
CARRIAGEWAY_M = 150.0  # unmeasured SKDR this close to a section = its 2nd carriageway/ramp
INTERCHANGE_M = 1000.0  # A/S crossing counts as a junction if a węzeł is this close
DW_NODE_M = 60.0       # regional roads: ends / T-junctions merge only this close (towns!)
DW_OVERLAP_M = 25.0    # regional-road pieces this close to a national road share its alignment


def as_line(geom):
    """Single LineString for a (possibly multi-part) section: join parts end to end."""
    if geom.geom_type == "LineString":
        return geom
    merged = linemerge(geom)
    if merged.geom_type == "LineString":
        return merged
    parts = list(merged.geoms)
    coords = list(parts[0].coords)
    rest = parts[1:]
    while rest:  # greedy chaining by nearest end
        tail = coords[-1]
        best = min(range(len(rest)), key=lambda i: min(
            Point(tail).distance(Point(rest[i].coords[0])),
            Point(tail).distance(Point(rest[i].coords[-1]))))
        p = rest.pop(best)
        c = list(p.coords)
        if Point(tail).distance(Point(c[-1])) < Point(tail).distance(Point(c[0])):
            c = c[::-1]
        coords.extend(c)
    return LineString(coords)


def uncounted_links(sec):
    """National roads without a GPR section (city-managed stretches, old alignments …)
    as junction-to-junction chains. Pieces near a section are second carriageways or
    ramps of counted roads and are dropped, so they don't form false parallel routes."""
    ctx = gpd.read_file(config.NETWORK_GPKG, layer="skdr_unmeasured")
    mids = gpd.GeoDataFrame(geometry=ctx.geometry.interpolate(0.5, normalized=True), crs=2180)
    near = gpd.sjoin_nearest(mids, sec[["geometry"]], max_distance=CARRIAGEWAY_M)
    ctx = ctx[~ctx.index.isin(near.index)]
    merged = linemerge(ctx.geometry.unary_union)
    chains = [g for g in getattr(merged, "geoms", [merged]) if g.length >= 50]
    ch = gpd.GeoDataFrame(geometry=chains, crs=2180)
    lab = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=ch.geometry.interpolate(0.5, normalized=True),
                                             crs=2180), ctx[["geometry", "NUMER_DROG"]])
    lab = lab[~lab.index.duplicated()]
    roads = lab["NUMER_DROG"].map(lambda v: sorted(skdr_tokens(v), key=str)[0]
                                  if skdr_tokens(v) else None)
    ch["road"] = roads.reindex(ch.index).values
    ch["road_class"] = ch["road"].map(lambda r: road_class(r) if r else None)
    ch["numer_odcinka"] = None
    ch["status"] = "uncounted"
    ch["dlugosc_km"] = ch["geom_km"] = (ch.length / 1000).round(3)
    return ch


def regional_links(sec, unc):
    """Regional roads (drogi wojewódzkie, BDOT10k) as uncounted links: merged per road
    number into chains; pieces sharing a national road's alignment are dropped.
    Also written as layer 'regional_roads' for the map."""
    dw = gpd.read_file(config.DW_GPKG).to_crs(2180).explode(index_parts=False)
    dw = dw[dw.geometry.geom_type == "LineString"].reset_index(drop=True)
    nat = gpd.GeoDataFrame(geometry=pd.concat([sec.geometry, unc.geometry]), crs=2180)
    mids = gpd.GeoDataFrame(geometry=dw.geometry.interpolate(0.5, normalized=True), crs=2180)
    near = gpd.sjoin_nearest(mids, nat, max_distance=DW_OVERLAP_M)
    dw = dw[~dw.index.isin(near.index)]
    num = dw["NUMER_DROG"].fillna("").astype(str).str.split(r"[|;,\s]+").str[0].str.strip()
    rows = []
    for n, g in dw.groupby(num):
        u = g.geometry.unary_union
        m = linemerge(u) if u.geom_type == "MultiLineString" else u
        for c in getattr(m, "geoms", [m]):
            if c.geom_type == "LineString" and c.length >= 50:
                rows.append(dict(road=f"DW{n}" if n else "DW", geometry=c))
    ch = gpd.GeoDataFrame(rows, crs=2180)
    ch["road_class"] = "DW"
    ch["numer_odcinka"] = None
    ch["status"] = "regional"
    ch["dlugosc_km"] = ch["geom_km"] = (ch.length / 1000).round(3)
    ch[["road", "geometry"]].to_file(config.NETWORK_GPKG, layer="regional_roads", driver="GPKG")
    return ch


def main():
    sec = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    sec["counted"] = True
    unc = uncounted_links(sec)
    unc["counted"] = False
    print(f"uncounted connector chains: {len(unc)}  ({unc.length.sum() / 1000:.0f} km)")
    dw = regional_links(sec, unc)
    dw["counted"] = False
    print(f"regional road chains: {len(dw)}  ({dw.length.sum() / 1000:,.0f} km)")
    sec = gpd.GeoDataFrame(pd.concat([sec, unc, dw], ignore_index=True), crs=2180)
    lines = [as_line(g) for g in sec.geometry]
    flat = np.array([c for ln in lines for c in (ln.coords[0][:2], ln.coords[-1][:2])])
    is_dw = (sec["road_class"] == "DW").values
    end_dw = np.repeat(is_dw, 2)

    # 1. endpoint clusters → nodes (national-road ends within NODE_MERGE_M; anything
    #    involving a regional road only within DW_NODE_M, so towns do not collapse)
    cl = nx.Graph()
    cl.add_nodes_from(range(len(flat)))
    ftree = cKDTree(flat)
    cl.add_edges_from((a, b) for a, b in ftree.query_pairs(NODE_MERGE_M)
                      if not (end_dw[a] or end_dw[b]))
    cl.add_edges_from(ftree.query_pairs(DW_NODE_M))
    end_node = np.empty(len(flat), int)
    node_xy, node_dw = [], []
    for nid, comp in enumerate(nx.connected_components(cl)):
        comp = list(comp)
        end_node[comp] = nid
        node_xy.append(flat[comp].mean(axis=0))
        node_dw.append(bool(end_dw[comp].all()))
    # 2. mid-section crossings become nodes (reusing a nearby endpoint node if any)
    wez = gpd.read_file(config.WEZLY_GPKG).to_crs(2180)
    wez = wez[wez["KAT_ISTNIE"] == "eksploatowany"]
    wez_tree = cKDTree(np.c_[wez.geometry.x, wez.geometry.y])
    end_tree = cKDTree(np.array(node_xy))
    tree = STRtree(lines)
    is_as = sec["road_class"].isin(["A", "S"]).values
    n_cross = 0
    for i, ln in enumerate(lines):
        for j in tree.query(ln, predicate="intersects"):
            if j <= i or sec.road.iloc[i] == sec.road.iloc[j] or not (
                    sec.counted.iloc[i] or sec.counted.iloc[j] or is_dw[i] or is_dw[j]):
                continue
            inter = ln.intersection(lines[j])
            pts = [inter] if inter.geom_type == "Point" else                 [g for g in getattr(inter, "geoms", []) if g.geom_type == "Point"]
            for p in pts:
                if (is_as[i] or is_as[j]) and not np.isfinite(
                        wez_tree.query((p.x, p.y), distance_upper_bound=INTERCHANGE_M)[0]):
                    continue
                r = DW_NODE_M if (is_dw[i] or is_dw[j]) else NODE_MERGE_M
                d, k = end_tree.query((p.x, p.y), distance_upper_bound=r)
                if not np.isfinite(d):
                    node_xy.append(np.array([p.x, p.y]))
                    node_dw.append(bool(is_dw[i] or is_dw[j]))
                    n_cross += 1
    node_xy = np.array(node_xy)

    # 3. T-junction splits (crossing nodes lie on both lines, so they split both)
    tree = STRtree(lines)
    cuts = defaultdict(dict)  # section idx → {distance along: node}
    for nid, (x, y) in enumerate(node_xy):
        p = Point(x, y)
        radius = DW_NODE_M if node_dw[nid] else TJUNCTION_M
        for i in tree.query(p.buffer(radius)):
            if nid in (end_node[2 * i], end_node[2 * i + 1]):
                continue
            ln = lines[i]
            if ln.distance(p) > (DW_NODE_M if is_dw[i] else radius):
                continue
            d = ln.project(p)
            if d < END_GUARD_M or d > ln.length - END_GUARD_M:
                continue
            if any(abs(d - e) < END_GUARD_M for e in cuts[i]):
                continue
            cuts[i][d] = nid

    rows = []
    attrs = sec.drop(columns="geometry")
    for i, ln in enumerate(lines):
        stops = [(0.0, end_node[2 * i])] + sorted(cuts[i].items()) + \
                [(ln.length, end_node[2 * i + 1])]
        for (d0, n0), (d1, n1) in zip(stops[:-1], stops[1:]):
            if n0 == n1 or d1 - d0 < 1:
                continue
            r = attrs.iloc[i].to_dict()
            r.update(from_node=int(n0), to_node=int(n1), geometry=substring(ln, d0, d1),
                     link_km=round((d1 - d0) / 1000, 3))
            rows.append(r)
    links = gpd.GeoDataFrame(rows, crs=2180)
    links.insert(0, "link_id", np.arange(len(links)))
    # vehicle-km/day on this link, scaled to official section length
    links["vkm_day"] = (links["sdrr_total"] * links["link_km"] / links["geom_km"].clip(lower=1e-3)
                        * links["dlugosc_km"]).round()

    used = set(links.from_node) | set(links.to_node)
    deg = links.groupby("from_node").size().add(links.groupby("to_node").size(), fill_value=0)
    roads = defaultdict(set)
    for f, t, r in zip(links.from_node, links.to_node, links.road):
        roads[f].add(str(r)) if isinstance(r, str) else None
        roads[t].add(str(r)) if isinstance(r, str) else None
    nodes = gpd.GeoDataFrame(
        [dict(node_id=n, x=node_xy[n][0], y=node_xy[n][1], degree=int(deg.get(n, 0)),
              roads=",".join(sorted(roads[n], key=str)), geometry=Point(node_xy[n]))
         for n in sorted(used)], crs=2180)

    net = nx.Graph()
    net.add_edges_from(zip(links.from_node, links.to_node))
    comps = sorted((len(c) for c in nx.connected_components(net)), reverse=True)
    print(f"lines: {len(sec)}  crossing nodes: {n_cross}  "
          f"link splits: {sum(len(c) for c in cuts.values())}")
    print(f"nodes: {len(nodes)}  links: {len(links)}  components: {len(comps)} "
          f"(largest {comps[0]} nodes = {comps[0] / net.number_of_nodes():.1%}; "
          f"next: {comps[1:6]})")
    print(f"links with counts: {links.counted.sum()}  uncounted: {(~links.counted).sum()} "
          f"({links.loc[~links.counted, 'link_km'].sum():.0f} km)")
    print(f"total traffic work: {links.vkm_day.sum() / 1e6:.1f} M veh-km/day")

    nodes.to_file(config.NETWORK_GPKG, layer="nodes", driver="GPKG")
    links.to_file(config.NETWORK_GPKG, layer="links", driver="GPKG")
    links.drop(columns="geometry").to_csv(config.OUT / f"links_{config.YEAR}.csv", index=False)
    nodes.drop(columns="geometry").to_csv(config.OUT / f"nodes_{config.YEAR}.csv", index=False)
    print("saved nodes/links layers + CSVs")


if __name__ == "__main__":
    main()
