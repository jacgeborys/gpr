"""
00b_fetch_osm.py — OSM main roads for Poland, used to patch holes in BDOT10k.

Reads highway = motorway | trunk | primary (+ their _link ramps) from the Geofabrik
extract poland-latest.osm.pbf (config.OSM_PBF; download it from
https://download.geofabrik.de/europe/poland/poland-latest.osm.pbf). Step 02 adds only the
OSM pieces BDOT10k does not have (unmapped interchange cores, roads opened after the BDOT
update, short holes) as costly fallback edges, so sections can be routed across gaps.

Also extracts the boundaries of the cities with powiat rights (config.POWIAT_CITIES,
OSM admin_level 6), drawn as pale areas on the map: GPR does not count national roads there.

Writes: data/osm/osm_main_roads.gpkg  layers 'roads' (EPSG:2180; osm_id, highway, ref, name,
        oneway) and 'cities' (name) — not in git. A few minutes per layer.
        Run `00b_fetch_osm.py roads` or `… cities` to refresh only one.
"""
import sys
import re

import geopandas as gpd
import osmium
import pandas as pd
from shapely.geometry import LineString

import config

HIGHWAY = re.compile(r"^(motorway|trunk|primary)(_link)?$")


def cities():
    from shapely import wkb
    fab = osmium.geom.WKBFactory()
    names = set(config.POWIAT_CITIES)
    found = {}
    fp = (osmium.FileProcessor(str(config.OSM_PBF))
          .with_areas(osmium.filter.TagFilter(("boundary", "administrative")))
          .with_filter(osmium.filter.EntityFilter(osmium.osm.AREA)))
    for a in fp:
        if a.tags.get("admin_level") == "6" and a.tags.get("name") in names and not a.from_way():
            found[a.tags["name"]] = wkb.loads(fab.create_multipolygon(a), hex=True)
    missing = sorted(names - set(found))
    g = gpd.GeoDataFrame({"name": list(found)}, geometry=list(found.values()), crs=4326).to_crs(2180)
    g.to_file(config.OSM_GPKG, layer="cities", driver="GPKG")
    print(f"saved {len(g)} city boundaries" + (f"; missing: {missing}" if missing else ""))


def junctions():
    """Named motorway/expressway interchanges (highway=motorway_junction), used in step 01
    to anchor section ends named 'W. <name>' (BDOT10k names only ~75% of its interchanges)."""
    from shapely.geometry import Point
    rows = []
    fp = (osmium.FileProcessor(str(config.OSM_PBF), osmium.osm.NODE)
          .with_filter(osmium.filter.TagFilter(("highway", "motorway_junction"))))
    for n in fp:
        name = n.tags.get("name")
        if name and n.location.valid():
            rows.append(dict(name=name, ref=n.tags.get("ref"),
                             geometry=Point(n.location.lon, n.location.lat)))
    g = gpd.GeoDataFrame(rows, crs=4326).to_crs(2180)
    g.to_file(config.OSM_GPKG, layer="junctions", driver="GPKG")
    print(f"saved {len(g)} named junction nodes")


def places():
    """Settlement names (place=city/town/village/hamlet/suburb/quarter/isolated_dwelling),
    used to locate GPR 2010 counting points, which come with a locality name but no coordinates."""
    from shapely.geometry import Point
    kinds = {"city", "town", "village", "hamlet", "suburb", "quarter", "neighbourhood",
             "isolated_dwelling", "locality"}
    rows = []
    fp = (osmium.FileProcessor(str(config.OSM_PBF), osmium.osm.NODE)
          .with_filter(osmium.filter.KeyFilter("place")))
    for n in fp:
        if n.tags.get("place") in kinds and n.tags.get("name") and n.location.valid():
            rows.append(dict(name=n.tags["name"], place=n.tags["place"],
                             geometry=Point(n.location.lon, n.location.lat)))
    g = gpd.GeoDataFrame(rows, crs=4326).to_crs(2180)
    g.to_file(config.OSM_GPKG, layer="places", driver="GPKG")
    print(f"saved {len(g)} place names")


def main():
    what = sys.argv[1:] or ["roads", "cities", "junctions", "places"]
    if not config.OSM_PBF.exists():
        raise SystemExit(f"missing {config.OSM_PBF}: download poland-latest.osm.pbf from Geofabrik")
    if "roads" in what:
        roads()
    if "cities" in what:
        cities()
    if "junctions" in what:
        junctions()
    if "places" in what:
        places()


def roads():
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
