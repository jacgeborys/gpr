"""
05_qa_report.py — quality metrics for the placed sections and the model network.

The key metrics are section-based (not "edges with any value"):
  * share of GPR sections / km placed on the map
  * geometry length vs official GPR length per section (len_ratio)
  * how each section was anchored, and QA flags

Reads : output/traffic_network_2025.gpkg
Writes: output/qa_report.md, output/qa_sections_to_review.csv, output/qa_gaps.csv,
        output/qa_dead_ends.csv
"""
import geopandas as gpd
import networkx as nx
import pandas as pd

import config

FLAG_HELP = {
    "scale": "km between counting points disagrees with route length by >25–33%",
    "chain_break": "route between counting points broken (missing link in BDOT10k); run split",
    "clipped": "road ended before the section's km ran out",
    "foreign": "extension had to follow a road with a different number",
    "partial": "one of the section's chainage pieces could not be placed",
    "none": "extension found nothing to follow",
    "gap_closed": "a break to the next section of the road was bridged (half of it added here)",
    "stitched": "end extended (along roads, or straight) to meet the next section / node",
    "trimmed": "line cut where a section of another road starts at the same-named interchange",
}


def visible_gaps(s):
    """Breaks in the drawn network: open BDOT stretches of a road that no section covers,
    with sections of that same road at both ends. Most are city-managed stretches (GPR
    does not count them, the section name says 'GR. MIASTA'); the rest are worth a look."""
    from shapely.geometry import Point
    from shapely.ops import linemerge, unary_union
    from common import skdr_tokens
    u = gpd.read_file(config.NETWORK_GPKG, layer="skdr_unmeasured")
    u["tok"] = u["NUMER_DROG"].map(skdr_tokens)
    rows = []
    for road in sorted({t for ts in u.tok for t in ts}, key=str):
        sec = s[s.road == road]
        if not len(sec):
            continue
        secu = unary_union(sec.geometry)
        uu = unary_union(u[u.tok.map(lambda t: road in t)].geometry)
        m = linemerge(uu) if uu.geom_type == "MultiLineString" else uu
        for ch in getattr(m, "geoms", [m]):
            a, b = Point(ch.coords[0]), Point(ch.coords[-1])
            if ch.length < 300 or a.distance(secu) > 150 or b.distance(secu) > 150:
                continue
            na, nb = (sec.iloc[sec.distance(p).argmin()] for p in (a, b))
            city = any("GR. MIASTA" in str(n.nazwa_odcinka) for n in (na, nb))
            c = ch.interpolate(0.5, normalized=True)
            rows.append(dict(road=road, gap_km=round(ch.length / 1000, 2), city=city,
                             x=round(c.x), y=round(c.y), section_a=na.numer_odcinka,
                             section_b=nb.numer_odcinka, name_a=na.nazwa_odcinka,
                             name_b=nb.nazwa_odcinka))
    return pd.DataFrame(rows).sort_values("gap_km", ascending=False)


def main():
    s = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    allsec = pd.read_csv(config.SECTIONS_CSV, dtype={"nr_drogi": str, "system": str, "road": str, "number": str})
    links = gpd.read_file(config.NETWORK_GPKG, layer="links")
    ok = s.len_ratio.between(0.8, 1.25)

    flags = s.qa_flags.fillna("").str.split(",").explode()
    flags = flags[flags != ""].value_counts()
    g = nx.Graph()
    g.add_edges_from(zip(links.from_node, links.to_node))
    comps = sorted((len(c) for c in nx.connected_components(g)), reverse=True)

    review = s[~ok | s.qa_flags.fillna("").ne("")].sort_values("dlugosc_km", ascending=False)
    review.drop(columns="geometry").to_csv(config.OUT / "qa_sections_to_review.csv", index=False)

    nodes = gpd.read_file(config.NETWORK_GPKG, layer="nodes")
    adm = gpd.read_file(config.BOUNDARY_SHP).to_crs(2180)
    border = adm[adm.RODZAJ == "województwo"].unary_union.boundary
    dead = nodes[(nodes.degree == 1) & (nodes.distance(border) > 3000)]
    dead.drop(columns="geometry").to_csv(config.OUT / "qa_dead_ends.csv", index=False)
    gaps = visible_gaps(s)
    gaps.to_csv(config.OUT / "qa_gaps.csv", index=False)
    top = s.nlargest(10, "sdrr_total")[["nr_drogi", "nazwa_odcinka", "sdrr_total"]]
    md = [f"# QA report — GPR {config.YEAR}", "",
          "## Sections", "",
          "| metric | value |", "|---|---|",
          f"| sections in GPR | {len(allsec)} ({allsec.dlugosc_km.sum():,.0f} km) |",
          f"| sections placed | {len(s)} ({s.dlugosc_km.sum():,.0f} km) |",
          f"| with SDRR | {s.sdrr_total.notna().sum()} |",
          f"| length within ±20–25% of GPR length | {ok.sum()} sections, "
          f"{s.loc[ok, 'dlugosc_km'].sum():,.0f} km ({s.loc[ok, 'dlugosc_km'].sum() / s.dlugosc_km.sum():.1%}) |",
          f"| median len_ratio | {s.len_ratio.median():.3f} |", "",
          "Placement: " + ", ".join(f"{k} {v}" for k, v in s.placement.value_counts().items()), "",
          "## QA flags", "", "| flag | sections | meaning |", "|---|---|---|"]
    md += [f"| {k} | {v} | {FLAG_HELP.get(k, '')} |" for k, v in flags.items()]
    md += ["", "## Status (from GPR remarks)", "", "| status | sections |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in s.status.value_counts().items()]
    md += ["", "## Model network", "", "| metric | value |", "|---|---|",
           f"| nodes | {g.number_of_nodes()} |",
           f"| links (counted / uncounted) | {links.counted.sum()} / {(~links.counted).sum()} |",
           f"| uncounted link km | {links.loc[~links.counted, 'link_km'].sum():,.0f} |",
           f"| connected components | {len(comps)} (largest {comps[0] / g.number_of_nodes():.1%}) |",
           f"| dead ends > 3 km from the border: national roads / regional roads | "
           f"{(~dead.roads.fillna('').str.contains('DW')).sum()} / "
           f"{dead.roads.fillna('').str.contains('DW').sum()} → `qa_dead_ends.csv` |",
           f"| traffic work | {links.vkm_day.sum() / 1e6:,.1f} M veh-km/day |", "",
           "## Busiest sections", "", "| road | section | SDRR |", "|---|---|---|"]
    md += [f"| {r.nr_drogi} | {r.nazwa_odcinka} | {r.sdrr_total:,.0f} |" for r in top.itertuples()]
    other = gaps[~gaps.city]
    md += ["", "## Visible gaps", "",
           f"{len(gaps)} uncovered stretches between sections of the same road "
           f"({gaps.gap_km.sum():,.0f} km); {int(gaps.city.sum())} next to a city-limit section "
           f"(city-managed, not counted by GPR) → `qa_gaps.csv`. Largest others:", "",
           "| road | km | between |", "|---|---|---|"]
    md += [f"| {r.road} | {r.gap_km} | {r.name_a} / {r.name_b} |" for r in other.head(12).itertuples()]
    md += ["", f"{len(review)} sections to review → `qa_sections_to_review.csv`", ""]
    (config.OUT / "qa_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
