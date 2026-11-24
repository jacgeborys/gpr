"""
00c_fetch_osm_history.py — the national road network as it was on a past date, from the
OpenStreetMap history (ohsome API, HeiGIT; © OpenStreetMap contributors).

GPR rounds before 2025 must be placed on the roads that existed then: in 2010 most of A1/A2
around Łódź and nearly all S-roads were not built. This downloads highway = motorway | trunk |
primary (+ links) valid on HISTORY_DATE[YEAR] in 1° tiles and keeps national roads (ref = a
1–2 digit number or A/S + number; links without ref are kept as connectors).

The output has the BDOT10k columns step 02 reads (NUMER_DROG, KAT_ISTNIE), so
    set GPR_YEAR=2010 && python 02_build_graph.py
builds the 2010 routing graph from it (config.SKDR_GPKG / GRAPH_PKL are year-specific).

Writes: data/osm/osm_roads_<YEAR>.gpkg (layer 'skdr_krajowe'), cached tiles in data/osm/ohsome_<YEAR>/
"""
import json
import re
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import shape

import config

URL = "https://api.ohsome.org/v1/elements/geometry"
HEADERS = {"User-Agent": "gpr-traffic-map/1.0 (research script)"}
HISTORY_DATE = {2010: "2010-07-01", 2015: "2015-07-01", 2020: "2020-07-01"}
FILTER = ("type:way and highway in (motorway, motorway_link, trunk, trunk_link, primary, "
          "primary_link)")
NATIONAL = re.compile(r"^(A|S|DK)?\s?\d{1,2}$", re.I)


def fetch(tile, date, cache):
    f = cache / f"{tile[0]:.0f}_{tile[1]:.0f}.geojson"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    w, s, e, n = tile
    for attempt in range(4):
        r = requests.post(URL, headers=HEADERS, timeout=600, data={
            "bboxes": f"{w},{s},{e},{n}", "time": date, "filter": FILTER,
            "properties": "tags"})
        if r.status_code == 200:
            f.write_text(r.text, encoding="utf-8")
            return r.json()
        print(f"  tile {tile}: HTTP {r.status_code}, retry")
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"tile {tile} failed")


def main():
    date = HISTORY_DATE[config.YEAR]
    cache = config.DATA / "osm" / f"ohsome_{config.YEAR}"
    cache.mkdir(parents=True, exist_ok=True)
    tiles = [(w, s, w + 1, s + 1) for s in np.arange(49, 55) for w in np.arange(14, 24)]
    rows = []
    for k, tile in enumerate(tiles, 1):
        js = fetch(tile, date, cache)
        for ft in js.get("features", []):
            p = ft["properties"]
            rows.append(dict(osm_id=p.get("@osmId"), highway=p.get("highway"),
                             ref=p.get("ref"), geometry=shape(ft["geometry"])))
        print(f"tile {k}/{len(tiles)}: {len(rows):,} ways so far", flush=True)
    g = gpd.GeoDataFrame(pd.DataFrame(rows), crs=4326).drop_duplicates("osm_id").to_crs(2180)
    g = g[g.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    refs = g["ref"].fillna("").str.split(";")
    national = refs.map(lambda rs: [x.strip().upper().replace("DK", "") for x in rs
                                    if NATIONAL.match(x.strip())])
    keep = national.map(bool) | (g["highway"].str.endswith("_link") & g["ref"].isna())
    g = g[keep].copy()
    g["NUMER_DROG"] = national[keep].map(lambda xs: "|".join(xs) if xs else None)
    g["KAT_ISTNIE"] = "eksploatowany"
    g["KAT_ZARZAD"] = "krajowa"
    out = config.DATA / "osm" / f"osm_roads_{config.YEAR}.gpkg"
    g[["osm_id", "highway", "ref", "NUMER_DROG", "KAT_ISTNIE", "KAT_ZARZAD", "geometry"]].to_file(
        out, layer="skdr_krajowe", driver="GPKG")
    print(f"saved {out}: {len(g):,} ways, {g.length.sum() / 1000:,.0f} km on {date}")
    print(g.groupby("highway").geometry.apply(lambda x: round(x.length.sum() / 1000)).to_string())


if __name__ == "__main__":
    main()
