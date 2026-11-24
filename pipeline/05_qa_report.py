"""
05_qa_report.py — quality metrics for the placed sections and the model network.

The key metrics are section-based (not "edges with any value"):
  * share of GPR sections / km placed on the map
  * geometry length vs official GPR length per section (len_ratio)
  * how each section was anchored, and QA flags

Reads : output/traffic_network_2025.gpkg
Writes: output/qa_report.md, output/qa_sections_to_review.csv
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
}


def main():
    s = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    allsec = pd.read_csv(config.SECTIONS_CSV)
    links = gpd.read_file(config.NETWORK_GPKG, layer="links")
    ok = s.len_ratio.between(0.8, 1.25)

    flags = s.qa_flags.fillna("").str.split(",").explode()
    flags = flags[flags != ""].value_counts()
    g = nx.Graph()
    g.add_edges_from(zip(links.from_node, links.to_node))
    comps = sorted((len(c) for c in nx.connected_components(g)), reverse=True)

    review = s[~ok | s.qa_flags.fillna("").ne("")].sort_values("dlugosc_km", ascending=False)
    review.drop(columns="geometry").to_csv(config.OUT / "qa_sections_to_review.csv", index=False)

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
           f"| traffic work | {links.vkm_day.sum() / 1e6:,.1f} M veh-km/day |", "",
           "## Busiest sections", "", "| road | section | SDRR |", "|---|---|---|"]
    md += [f"| {r.nr_drogi} | {r.nazwa_odcinka} | {r.sdrr_total:,.0f} |" for r in top.itertuples()]
    md += ["", f"{len(review)} sections to review → `qa_sections_to_review.csv`", ""]
    (config.OUT / "qa_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
