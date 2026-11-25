"""
01_parse_gpr2010.py — GPR 2010 (national roads) into the same tables as 01_parse_gpr.py,
so steps 03 / 03b / 05 / 06 run on it unchanged (set GPR_YEAR=2010).

Input (config.GPR2010_DIR, PDFs from the GDDKiA archive):
  0113_Wykaz_odc_pomiarowych_GPR_2010.pdf    Tablica 1: sections, chainage, counting-point km
                                             and locality
  0114_SDR_w_pkt_pomiarowych_w_2010_roku.pdf Tablica 2: SDR (motor vehicles) by class

2010 counting points have no coordinates; they are located
  A) by chainage on the placed 2025 network: a 2025 section of the same chainage system whose
     km range holds the point's km (2025 geometry, linear by km), and
  B) by the locality name: an OSM place of that name (step 00b 'places') next to a road with
     that number (projected onto the road).
  If both exist and agree within AGREE_M, A is used (more precise); if they disagree, the road
  was renumbered / re-chained since 2010 and B is used; otherwise whichever exists.

Writes: output/gpr2010_sections.csv, output/gpr2010_pieces.csv, output/gpr2010_points.gpkg
"""
import math
import pickle
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pdfplumber
from shapely.geometry import Point
from shapely.ops import linemerge
from shapely.strtree import STRtree

import config
from common import road_class, system_base, to_float

AGREE_M = 4000      # A and B positions closer than this: chainage still valid, use A
PLACE_ROAD_M = 3000  # a locality must lie this close to the road to locate a counting point
ANY_ROAD_M = 1500    # … or this close to any national road when the 2010 number is gone

T1_COLS = ["numer_odcinka", "nr_drogi", "nr_europejski", "pik_pocz", "pik_konc", "dlugosc_km",
           "nazwa_odcinka", "typ_odcinka", "pik_punktu", "miejscowosc", "pomiar_dodatkowy",
           "nazwa_rejonu", "nr_rejonu", "odcinek_gpr2005", "sdr_2005"]
T2_COLS = ["numer_odcinka", "nr_drogi", "nr_europejski", "pik_pocz", "pik_konc", "dlugosc_km",
           "nazwa_odcinka", "sdrr_total", "sdrr_motocykle", "sdrr_sam_osobowe",
           "sdrr_lekkie_ciezarowe", "sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy",
           "sdrr_ciagniki", "rowery"]


def read_table(path, cols):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tab in page.extract_tables():
                for r in tab:
                    if r and r[0] and re.fullmatch(r"\d{5}", str(r[0]).strip()):
                        r = [(str(c).replace("\n", " ").strip() if c is not None else None)
                             for c in r[:len(cols)]]
                        rows.append(r + [None] * (len(cols) - len(r)))
    df = pd.DataFrame(rows, columns=cols)
    return pd.concat([df, text_rows(path, cols, set(df.numer_odcinka), df)], ignore_index=True)


NUM = r"\d+(?:,\d+)?"


def text_rows(path, cols, have, df):
    """Rows the table grid loses (merged cells leave the section number empty, e.g. 40205
    Koziegłowy–Siewierz): parse their text line instead."""
    out = []
    head = rf"^(\d{{5}}) (\S+)(?: (E\d+))? ({NUM}) ({NUM}) ({NUM}) "
    rejon = dict(zip(df.nr_rejonu, df.nazwa_rejonu)) if "nr_rejonu" in df else {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for ln in (page.extract_text() or "").splitlines():
                m = re.match(head, ln)
                if not m or m.group(1) in have:
                    continue
                rest = ln[m.end():]
                base = list(m.groups())
                if "sdrr_total" in cols:          # Tablica 2: name + 9 counts
                    t = re.fullmatch(r"(.+?)((?: \d+){9})", rest)
                    if not t:
                        continue
                    r = base + [t.group(1).strip()] + t.group(2).split()
                else:                             # Tablica 1: name typ km locality … rejon nr
                    t = re.fullmatch(r"(.+?) ([GH]) (\S+) (.+) (\d{3}) (\d{5})(?: (\S+))?", rest)
                    if not t:
                        continue
                    name, typ, pk, mid, nr, o05, sdr05 = t.groups()
                    rn = rejon.get(nr, "")
                    if rn and mid.endswith(" " + rn):
                        mid = mid[:-len(rn) - 1]
                    extra = None
                    if mid.endswith(" *"):
                        mid, extra = mid[:-2], "*"
                    r = base + [name, typ, pk, mid, extra, rn, nr, o05, sdr05]
                have.add(m.group(1))
                out.append(r[:len(cols)])
                print(f"  from text (lost by the table grid): {ln}")
    return pd.DataFrame(out, columns=cols)


def point_km(v):
    """'21,6' → 21.6; 'P-13.2 L-13.4' → 13.3 (mean of right/left)."""
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(v or ""))]
    return float(np.mean(nums)) if nums else float("nan")


def norm_tokens(name):
    out = []
    for tok in re.split(r"[\s\-/]+", str(name).upper()):
        if tok:
            out.append((tok.rstrip("."), tok.endswith(".")))
    return out


def same_place(gpr, osm):
    if len(gpr) != len(osm):
        return False
    return all(o == g or (abbr and o.startswith(g)) for (g, abbr), (o, _) in zip(gpr, osm))


def main():
    t1 = read_table(config.GPR2010_DIR / "0113_Wykaz_odc_pomiarowych_GPR_2010.pdf", T1_COLS)
    t2 = read_table(config.GPR2010_DIR / "0114_SDR_w_pkt_pomiarowych_w_2010_roku.pdf", T2_COLS)
    t1 = t1.drop_duplicates("numer_odcinka")
    t2 = t2.drop_duplicates("numer_odcinka")
    s = t1.merge(t2[["numer_odcinka"] + T2_COLS[7:]], on="numer_odcinka", how="left")
    s["numer_odcinka"] = s["numer_odcinka"].astype(int)
    for c in ("pik_pocz", "pik_konc", "dlugosc_km"):
        s[c] = s[c].map(to_float)
    for c in T2_COLS[7:]:
        s[c] = pd.to_numeric(s[c].astype(str).str.replace(r"\s", "", regex=True), errors="coerce")
    print(f"GPR 2010 sections: {len(s)} (Tablica 1 {len(t1)}, Tablica 2 {len(t2)}), "
          f"with SDR: {s.sdrr_total.notna().sum()}")

    s["nr_drogi"] = s["nr_drogi"].astype(str).str.strip()
    s["system"] = s["nr_drogi"]
    s["road"] = s["system"].map(lambda x: system_base(x)[0])
    s["road_class"] = s["road"].map(road_class)
    s["status"] = np.where(s["sdrr_total"].notna(), "measured", "no_data")
    s["sdrr_mikrobusy"] = np.nan   # in 2010 counted with cars
    s["sdrr_heavy"] = s[["sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy",
                         "sdrr_ciagniki"]].sum(axis=1, min_count=1)
    s["heavy_share"] = (s["sdrr_heavy"] / s["sdrr_total"]).round(3)
    s["pk"] = s["pik_punktu"].map(point_km)
    # 'WĘZEŁ RUSOCIN-WĘZEŁ STANISŁAWIE' → 'W. RUSOCIN - W. STANISŁAWIE' (2025 style, so step 01's
    # interchange lookup and step 03's name hints work)
    def restyle(n):
        n = str(n).replace("WĘZEŁ ", "W. ").replace("/WĘZEŁ/", "")
        parts = n.split("-")
        return " - ".join(p.strip() for p in parts) if len(parts) == 2 else n
    s["nazwa_odcinka"] = s["nazwa_odcinka"].map(restyle)
    for c in ("nr_woj", "uwagi", "odcinek_gpr2020", "side_used"):
        s[c] = np.nan
    s["nr_woj"] = (s["numer_odcinka"] // 1000).astype(int)

    # ── A: by chainage on the 2025 network ───────────────────────────────────────────
    net25 = config.OUT / "traffic_network_2025.gpkg"
    sec25 = gpd.read_file(net25, layer="sections")
    sec25 = sec25[sec25.nr_drogi.astype(str).str.contains("\n") == False]   # single-system only
    sec25 = sec25[sec25.len_ratio.between(0.75, 1.33)]
    by_sys = {k: g for k, g in sec25.groupby("system")}
    ax, ay = np.full(len(s), np.nan), np.full(len(s), np.nan)
    for k, r in enumerate(s.itertuples()):
        g = by_sys.get(r.system)
        if g is None or np.isnan(r.pk):
            continue
        hit = g[(g.pik_pocz <= r.pk) & (g.pik_konc >= r.pk)]
        if not len(hit):
            continue
        h = hit.iloc[0]
        line = h.geometry if h.geometry.geom_type == "LineString" else linemerge(h.geometry)
        if line.geom_type != "LineString":
            continue
        f = (r.pk - h.pik_pocz) / max(h.pik_konc - h.pik_pocz, 1e-6)
        p = line.interpolate(f, normalized=True)
        ax[k], ay[k] = p.x, p.y

    # ── B: by locality name, next to a road with that number ─────────────────────────
    D = pickle.load(open(config.GRAPH_PKL, "rb"))
    G, GEOMS = D["G"], D["geoms"]
    road_edges = {}
    for u, v, d in G.edges(data=True):
        for t in d["tok"]:
            road_edges.setdefault(t, []).append(GEOMS[d["eid"]])
    road_tree = {t: STRtree(gs) for t, gs in road_edges.items()}
    places = gpd.read_file(config.OSM_GPKG, layer="places")
    places["tok"] = places["name"].map(norm_tokens)
    by_first = {}
    for k, tk in enumerate(places["tok"]):
        if tk:
            by_first.setdefault(tk[0][0], []).append(k)
    px, py = places.geometry.x.values, places.geometry.y.values
    all_geoms = list(GEOMS)
    all_tree = STRtree(all_geoms)

    def nearest_on(tree, geoms, pt, radius):
        best = None
        for e in tree.query(pt.buffer(radius)):
            d = geoms[e].distance(pt)
            if d <= radius and (best is None or d < best[0]):
                q = geoms[e].interpolate(geoms[e].project(pt))
                best = (d, q.x, q.y)
        return best

    bx, by = np.full(len(s), np.nan), np.full(len(s), np.nan)
    located_any = np.zeros(len(s), bool)
    for k, r in enumerate(s.itertuples()):
        name = re.sub(r"[.*]", " ", str(r.miejscowosc or "")).split(" UL")[0].strip()
        if not name:
            continue
        gt = norm_tokens(name)
        cand = [j for j in by_first.get(gt[0][0], []) if same_place(gt, places["tok"].iat[j])]
        best = None
        if r.road in road_tree:
            for j in cand:
                b = nearest_on(road_tree[r.road], road_edges[r.road], Point(px[j], py[j]),
                               PLACE_ROAD_M)
                if b and (best is None or b[0] < best[0]):
                    best = b
        if best is None:
            # road renumbered since 2010 (old DK1 Gdańsk–Łódź is DK91 now, DK3/5/7 moved onto
            # S3/S5/S7): nearest national road of any number
            for j in cand:
                b = nearest_on(all_tree, all_geoms, Point(px[j], py[j]), ANY_ROAD_M)
                if b and (best is None or b[0] < best[0]):
                    best = b
            located_any[k] = best is not None
        if best:
            bx[k], by[k] = best[1], best[2]

    hasA, hasB = ~np.isnan(ax), ~np.isnan(bx)
    agree = hasA & hasB & (np.hypot(ax - bx, ay - by) < AGREE_M)
    useA = hasA & (~hasB | agree)
    s["x"] = np.where(useA, ax, bx)
    s["y"] = np.where(useA, ay, by)
    s["located_by"] = np.where(useA, "chainage_2025", np.where(hasB, "locality", None))
    print(f"counting points located: by 2025 chainage {useA.sum()}, by locality "
          f"{(~useA & hasB).sum()} (A and B disagreed: {(hasA & hasB & ~agree).sum()}), "
          f"not located {(~hasA & ~hasB).sum()}; on a road with another number now: "
          f"{(located_any & ~useA).sum()}")
    ll = gpd.GeoSeries(gpd.points_from_xy(s.x, s.y), crs=2180).to_crs(4326)
    s["lat"], s["lon"] = np.where(s.x.notna(), ll.y, np.nan), np.where(s.x.notna(), ll.x, np.nan)

    # pieces: one per section (2010 tables have one chainage system per section)
    s["pk_in_section"] = (s.pk >= s.pik_pocz - 1.0) & (s.pk <= s.pik_konc + 1.0)
    pieces = pd.DataFrame(dict(numer_odcinka=s.numer_odcinka, part=0, system=s.system,
                               road=s.road, number=s.road.str.lstrip("AS"), p0=s.pik_pocz,
                               p1=s.pik_konc, anchor=s.pk_in_section & s.x.notna()))
    pieces = pieces.dropna(subset=["p0", "p1"])

    # interchange anchors as for 2025 (step 01)
    import importlib
    p01 = importlib.import_module("01_parse_gpr")
    p01.locate_junctions(s)

    s.to_csv(config.SECTIONS_CSV, index=False, encoding="utf-8")
    pieces.to_csv(config.PIECES_CSV, index=False, encoding="utf-8")
    g = gpd.GeoDataFrame(s.dropna(subset=["x"]), geometry=gpd.points_from_xy(
        s.dropna(subset=["x"]).x, s.dropna(subset=["x"]).y), crs=2180)
    g.to_file(config.POINTS_GPKG, layer="counting_points", driver="GPKG")
    print(f"saved {config.SECTIONS_CSV.name}, pieces, {config.POINTS_GPKG.name}")


if __name__ == "__main__":
    if config.YEAR != 2010:
        raise SystemExit("set GPR_YEAR=2010 to run this step")
    main()
