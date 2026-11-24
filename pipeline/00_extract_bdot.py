"""
00_extract_bdot.py — extract national roads (OT_SKDR_L, KAT_ZARZAD='krajowa') from
the BDOT10k country archive, keeping ALL attributes (incl. KAT_ISTNIE = operational /
under construction) and full-resolution geometry (no simplification).

Reads : config.BDOT_ZIP  (Polska_SHP.zip: one nested ZIP per voivodeship)
Writes: config.SKDR_GPKG (layer 'skdr_krajowe', EPSG:2180)

Only needs re-running when a new BDOT10k snapshot is downloaded (~7 min).
"""
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

import config

TMP = config.DATA / "bdot" / "_tmp"


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    frames = []
    with zipfile.ZipFile(config.BDOT_ZIP) as outer:
        regions = [f for f in outer.filelist if f.filename.endswith(".zip")]
        for zi in regions:
            outer.extract(zi, TMP)
            nested = TMP / zi.filename
            with zipfile.ZipFile(nested) as inner:
                names = [n for n in inner.namelist() if "SKDR_L" in n.upper()]
                for n in names:
                    (TMP / Path(n).name).write_bytes(inner.read(n))
            nested.unlink()
            for shp in TMP.glob("*SKDR_L.shp"):
                g = gpd.read_file(shp, encoding="utf-8")
                g = g[g["KAT_ZARZAD"] == "krajowa"].copy()
                g["region"] = zi.filename.split(".")[-2] if "." in zi.filename else zi.filename
                frames.append(g)
                print(f"{shp.name}: {len(g):,} national-road features", flush=True)
            for f in TMP.glob("*"):
                if f.is_file():
                    f.unlink()
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs).to_crs(2180)
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    print("columns:", list(out.columns))
    for c in ("KAT_ISTNIE", "KLASA_DROG"):
        if c in out.columns:
            print(out[c].value_counts(dropna=False).to_string())
    out.to_file(config.SKDR_GPKG, layer="skdr_krajowe", driver="GPKG")
    print(f"saved {config.SKDR_GPKG}: {len(out):,} features")
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
