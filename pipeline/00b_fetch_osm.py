"""
00b_fetch_osm.py — OSM main roads for Poland, used to patch holes in BDOT10k.

Reads highway = motorway | trunk | primary (+ their _link ramps) from the Geofabrik
extract poland-latest.osm.pbf (config.OSM_PBF; download it from
https://download.geofabrik.de/europe/poland/poland-latest.osm.pbf). Step 02 adds only the
OSM pieces BDOT10k does not have (unmapped interchange cores, roads opened after the BDOT
update, short holes) as costly fallback edges, so sections can be routed across gaps.

Writes: data/osm/osm_main_roads.gpkg  (layer 'roads', EPSG:2180; osm_id, highway, ref,
        name, oneway) — not in git. Takes a few minutes (the whole extract is scanned).
"""
import re

import geopandas as gpd
import osmium
import pandas as pd
from shapely.geometry import LineString

import config

HIGHWAY = re.compile(r"^(motorway|trunk|primary)(_link)?$")


def main():
    if not config.OSM_PBF.exists():
        raise SystemExit(f"missing {config.OSM_PBF}: download poland-latest.osm.pbf from Geofabrik")
    rows = []
    fp = (osmium.FileProcessor(str(config.OSM_PBF), osmium.osm.WAY | osmium.osm.NODE)
          .with_locations()
          .with_filter(osmium.filter.KeyFilter("highway")))
    for w in fp:
        if not w.is_way():
            continue
        hw = w.tags.get("highway", "")
        if not HIGHWAY.match(hw):
            continue
        # built but not open to traffic (e.g. S19 south of Boćki in 2025)
        if (w.tags.get("access") in ("no", "private") or w.tags.get("motor_vehicle") == "no"
                or "construction" in w.tags or "proposed" in w.tags):
            continue
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            continue
        if len(coords) < 2:
            continue
        rows.append(dict(osm_id=w.id, highway=hw, ref=w.tags.get("ref"),
                         name=w.tags.get("name"), oneway=w.tags.get("oneway"),
                         geometry=LineString(coords)))
    g = gpd.GeoDataFrame(pd.DataFrame(rows), crs=4326).to_crs(2180)
    config.OSM_GPKG.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(config.OSM_GPKG, layer="roads", driver="GPKG")
    print(f"saved {config.OSM_GPKG}: {len(g):,} ways, {g.length.sum() / 1000:,.0f} km")
    print(g.groupby("highway").geometry.apply(lambda x: round(x.length.sum() / 1000)).to_string())


if __name__ == "__main__":
    main()
