"""
06_render_cartogram.py — static traffic flow map in light and dark themes:
line width ∝ SDRR, colour continuous along the SDRR class ramp (config.SDRR_BREAKS /
SDRR_COLORS_*: each class colour at its class middle, as in the legend), font Bahnschrift.

Reads : output/traffic_network_2025.gpkg, config.BOUNDARY_SHP
Writes: output/cartogram_2025_light.png, output/cartogram_2025_dark.png

--trucks (with --dw): two truck maps (trucks = samochody ciężarowe bez + z przyczepą):
  cartogram_<year>_dkdw_trucks_*.png      width ∝ SDRR in the 'other vehicles' colour with a
                                          truck-coloured core, core width / line width = truck share
  cartogram_<year>_dkdw_truckshare_*.png  width ∝ SDRR, colour = truck share (TRUCK_SHARE_BREAKS)
"""
import sys

import geopandas as gpd
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import config  # noqa: E402

THEMES = {
    "light": dict(bg="#fcfcfb", land="#f3f2ef", city="#dbd8d0", border="#d6d5cf", ctx=config.NO_COUNT_LIGHT,
                  text="#0b0b0b", text2="#52514e", ramp=config.SDRR_COLORS_LIGHT),
    "dark": dict(bg="#1a1a19", land="#232322", city="#3a3a36", border="#3a3a37", ctx=config.NO_COUNT_DARK,
                 text="#f0efec", text2="#c3c2b7", ramp=config.SDRR_COLORS_DARK),
}
FONT_FILE = "C:/Windows/Fonts/bahnschrift.ttf"
SDRR_MAX = 120_000           # width/colour saturate here (a handful of urban A4/S8 links exceed it)
W_MIN, W_MAX = 0.35, 9.0     # line width in points
FIG_W = 12.0                 # inches; height follows the country's aspect ratio
PAD_M, PAD_TOP_M = 8_000, 80_000  # frame margins around the country (m)
CITIES = {"Warszawa": (21.01, 52.23), "Kraków": (19.94, 50.06), "Łódź": (19.46, 51.76),
          "Wrocław": (17.03, 51.11), "Poznań": (16.93, 52.41), "Gdańsk": (18.65, 54.35),
          "Szczecin": (14.55, 53.43), "Katowice": (19.02, 50.26), "Lublin": (22.57, 51.25),
          "Białystok": (23.16, 53.13), "Rzeszów": (22.00, 50.04), "Bydgoszcz": (18.01, 53.12),
          "Olsztyn": (20.49, 53.78), "Kielce": (20.63, 50.87), "Zielona Góra": (15.51, 51.94)}
# truck maps: colours of the composition map and the share classes of the share map
TRUCK_COLORS = {"light": dict(car="#7fb0dc", truck="#d0312d"),
                "dark": dict(car="#2f8fb3", truck="#ff6a55")}
CORE_MIN_PT = 0.45   # truck cores thinner than ~1.25 px (at 200 dpi) are left out: they'd blend
TRUCK_SHARE_BREAKS = [0.05, 0.10, 0.15, 0.20, 0.30]
TRUCK_SHARE_RAMP = {"light": ["#2a6fbb", "#5f78c6", "#9068b6", "#c2519a", "#de3a57", "#a8121c"],
                    "dark": ["#3fa7d6", "#6f9be6", "#a98be6", "#e27ac4", "#ff6b7d", "#ff3b30"]}
# candidate share ramps with a lightness step (OKLCH), colour-blind friendlier; try with
# --ramp A|B|C → cartogram_<year>_dkdw_truckshare_<X>_*.png
TRUCK_SHARE_VARIANTS = {
    "A": {"light": ["#69a1e8", "#857fd7", "#a059b1", "#ab3276", "#a5092a", "#8a0314"],
          "dark": ["#3d73b6", "#7973ca", "#b76ec7", "#e96cad", "#ff8386", "#ffa098"]},
    "B": {"light": ["#97c1f7", "#9995e8", "#ab62bb", "#ae2c77", "#950024", "#6a000b"],
          "dark": ["#2b568b", "#655eb3", "#aa62ba", "#e669aa", "#fe8f90", "#febab4"]},
    "C": {"light": ["#418ad1", "#78b3d6", "#fc9e47", "#e86518", "#c92516", "#8a0314"],
          "dark": ["#2a75ba", "#579bc2", "#ffa659", "#fd7933", "#f14634", "#df202e"]},
}
RAMP_TAG = ""
LABEL_BELOW = {"Rzeszów", "Olsztyn"}   # labelled bottom right so they don't cover the A4 / S51-S16


def use_font():
    try:
        font_manager.fontManager.addfont(FONT_FILE)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT_FILE).get_name()
    except (OSError, RuntimeError):
        print(f"font {FONT_FILE} not found, using the default")


def smooth_color(v, ramp, breaks=None, vmax=SDRR_MAX):
    """Continuous colour: each class colour sits at its class middle (the legend swatch value)
    and colours blend linearly in between, so local differences inside a class show."""
    from matplotlib.colors import to_rgb
    b = [0] + (config.SDRR_BREAKS if breaks is None else breaks) + [vmax]
    mids = [(lo + hi) / 2 for lo, hi in zip(b[:-1], b[1:])]
    if v <= mids[0]:
        return to_rgb(ramp[0])
    if v >= mids[-1]:
        return to_rgb(ramp[-1])
    k = int(np.searchsorted(mids, v)) - 1
    f = (v - mids[k]) / (mids[k + 1] - mids[k])
    a, c = np.array(to_rgb(ramp[k])), np.array(to_rgb(ramp[k + 1]))
    return tuple(a + (c - a) * f)


def sdrr_class(v):
    return int(np.searchsorted(config.SDRR_BREAKS, v, side="right"))


def class_labels():
    f = lambda v: f"{v:,.0f}".replace(",", " ")
    b = config.SDRR_BREAKS
    return ([f"< {f(b[0])}"] + [f"{f(lo)} – {f(hi)}" for lo, hi in zip(b[:-1], b[1:])]
            + [f"> {f(b[-1])}"])


def width(v):
    return W_MIN + (W_MAX - W_MIN) * np.clip(v / SDRR_MAX, 0, 1)


def segs(geom):
    parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
    return [np.asarray(p.coords)[:, :2] for p in parts]


class BlobHandler:
    """Legend key for city areas: an irregular blob, so it does not read as a wide line."""
    SHAPE = [(0.05, 0.45), (0.12, 0.15), (0.35, 0.0), (0.55, 0.12), (0.8, 0.02), (0.97, 0.3),
             (0.88, 0.62), (0.95, 0.9), (0.62, 1.0), (0.42, 0.82), (0.18, 0.95), (0.0, 0.72)]

    def legend_artist(self, legend, orig_handle, fontsize, handlebox):
        from matplotlib.patches import Polygon
        x0, y0 = handlebox.xdescent, handlebox.ydescent
        w, h = handlebox.width, handlebox.height * 1.6
        x0 += w * 0.2
        w *= 0.6
        y0 -= handlebox.height * 0.3
        poly = Polygon([(x0 + px * w, y0 + py * h) for px, py in self.SHAPE], closed=True,
                       facecolor=orig_handle.get_facecolor(), edgecolor="none",
                       transform=handlebox.get_transform())
        handlebox.add_artist(poly)
        return poly


def render(theme, sec, ctx, dw, voiv, country, cities=None, dwsec=None, mode=None):
    t = THEMES[theme]
    # frame = country bounds + small margins (extra on top for the title over the Baltic);
    # the axes fill the whole figure, so Poland fills the frame
    minx, miny, maxx, maxy = country.total_bounds
    x0, x1, y0, y1 = minx - PAD_M, maxx + PAD_M, miny - PAD_M, maxy + PAD_TOP_M
    fig = plt.figure(figsize=(FIG_W, FIG_W * (y1 - y0) / (x1 - x0)), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.patch.set_facecolor(t["bg"])
    ax.set_facecolor(t["bg"])
    country.plot(ax=ax, color=t["land"], edgecolor="none")
    if cities is not None and len(cities):   # cities with powiat rights: GPR does not count there
        cities.plot(ax=ax, color=t["city"], edgecolor="none", zorder=1)
    # internal admin borders omitted: granice_admin pieces do not share edges cleanly
    country.boundary.plot(ax=ax, color=t["border"], linewidth=0.9)
    if dw is not None and len(dw):   # regional roads: no traffic data, thin context
        ax.add_collection(LineCollection([s for g in dw.geometry for s in segs(g)],
                                         colors=t["ctx"], linewidths=0.35, capstyle="round",
                                         zorder=1.5))
    ax.add_collection(LineCollection([s for g in ctx.geometry for s in segs(g)],
                                     colors=t["ctx"], linewidths=0.9, capstyle="round", zorder=2))
    nodata = sec[sec.sdrr_total.isna()]
    ax.add_collection(LineCollection([s for g in nodata.geometry for s in segs(g)],
                                     colors=t["ctx"], linewidths=1.0, linestyles=(0, (1, 1.2)),
                                     zorder=3))
    data = sec[sec.sdrr_total.notna()]
    cols = ["sdrr_total", "trucks", "geometry"]
    if dwsec is not None:   # regional sections share the scale; thick lines drawn on top
        data = pd.concat([data[cols], dwsec[cols]])
    data = data.sort_values("sdrr_total")
    if mode == "trucks":
        # composition: line in the 'other vehicles' colour, truck core inside it. Drawn in
        # chunks (lines, then their cores) so thin roads' cores do not cross thick roads
        tc = TRUCK_COLORS[theme]
        chunk = 400
        for i in range(0, len(data), chunk):
            part = data.iloc[i:i + chunk]
            lines, ws, cores, cws = [], [], [], []
            for g, v, tr in zip(part.geometry, part.sdrr_total, part.trucks):
                cw = width(v) * min(tr / v, 1.0)
                for s in segs(g):
                    lines.append(s)
                    ws.append(width(v))
                    if cw >= CORE_MIN_PT:   # thinner cores antialias into purple: not drawn
                        cores.append(s)
                        cws.append(cw)
            z = 4 + i / len(data)
            ax.add_collection(LineCollection(lines, linewidths=ws, colors=tc["car"],
                                             capstyle="round", joinstyle="round", zorder=z))
            ax.add_collection(LineCollection(cores, linewidths=cws, colors=tc["truck"],
                                             capstyle="round", joinstyle="round",
                                             antialiased=False,   # pure red, no blend into blue
                                             zorder=z + 0.5 * chunk / len(data)))
    else:
        lines, ws, cs = [], [], []
        for g, v, tr in zip(data.geometry, data.sdrr_total, data.trucks):
            c = (smooth_color(tr / v, TRUCK_SHARE_RAMP[theme], TRUCK_SHARE_BREAKS, 0.4)
                 if mode == "truckshare" else smooth_color(v, t["ramp"]))
            for s in segs(g):
                lines.append(s)
                ws.append(width(v))
                cs.append(c)
        ax.add_collection(LineCollection(lines, linewidths=ws, colors=cs, capstyle="round",
                                         joinstyle="round", zorder=4))

    pts = gpd.GeoSeries(gpd.points_from_xy([c[0] for c in CITIES.values()],
                                           [c[1] for c in CITIES.values()]), crs=4326).to_crs(2180)
    for name, p in zip(CITIES, pts):
        ax.plot(p.x, p.y, "o", ms=3, color=t["text"], zorder=5)
        below = name in LABEL_BELOW   # label bottom right, off a road running east-west
        ax.annotate(name, (p.x, p.y), xytext=(5, -4 if below else 4), textcoords="offset points",
                    fontsize=9, va="top" if below else "baseline",
                    color=t["text"], zorder=6, fontweight="medium",
                    path_effects=[matplotlib.patheffects.withStroke(linewidth=2.5,
                                                                    foreground=t["bg"])])

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")

    title = "krajowych i wojewódzkich" if dwsec is not None else "krajowych"
    head = {None: f"Ruch na drogach {title} {config.YEAR}",
            "trucks": f"Samochody ciężarowe na drogach {title} {config.YEAR}",
            "truckshare": f"Udział samochodów ciężarowych na drogach {title} {config.YEAR}"}[mode]
    sub = {None: "Średni dobowy ruch roczny (SDRR), pojazdy/dobę",
           "trucks": "Szerokość linii: SDRR (wszystkie pojazdy), czerwony rdzeń: samochody ciężarowe",
           "truckshare": "Kolor: udział samochodów ciężarowych w SDRR, szerokość linii: SDRR"}[mode]
    fig.text(0.025, 0.965, head, fontsize=24, color=t["text"], va="top")
    fig.text(0.025, 0.935, f"{sub} · Generalny Pomiar Ruchu GDDKiA {config.YEAR}", fontsize=11,
             color=t["text2"], va="top")

    fmt = lambda v: f"{v:,.0f}".replace(",", " ")
    if mode is None:
        # class legend: colour + width of each class (width at the class middle), flat ends
        b = [0] + config.SDRR_BREAKS + [SDRR_MAX]
        mids = [(lo + hi) / 2 for lo, hi in zip(b[:-1], b[1:])]
        handles = [Line2D([], [], color=c, lw=width(m), solid_capstyle="butt", label=lab)
                   for c, m, lab in zip(t["ramp"], mids, class_labels())][::-1]
        leg_title = "SDRR [pojazdy/dobę]"
    elif mode == "trucks":
        tc = TRUCK_COLORS[theme]
        handles = [Line2D([], [], color=tc["car"], lw=width(v), solid_capstyle="butt",
                          label=fmt(v)) for v in (100_000, 50_000, 20_000, 5_000)]
        leg_title = "SDRR [pojazdy/dobę]"
    else:
        ramp = TRUCK_SHARE_RAMP[theme]
        b = [0] + TRUCK_SHARE_BREAKS
        labs = ([f"< {b[1]:.0%}"] + [f"{lo:.0%} – {hi:.0%}" for lo, hi in zip(b[1:-1], b[2:])]
                + [f"> {b[-1]:.0%}"])
        handles = [Line2D([], [], color=c, lw=5, solid_capstyle="butt", label=lab)
                   for c, lab in zip(ramp, labs)][::-1]
        leg_title = "Udział samochodów ciężarowych"
    leg = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.01, 0.035),
                    frameon=False, fontsize=9.5, labelcolor=t["text2"],
                    title=leg_title, title_fontsize=11, handlelength=3.4,
                    borderaxespad=0.2, alignment="left")
    leg.get_title().set_color(t["text"])
    ax.add_artist(leg)
    if mode == "trucks":
        # composition key: a fixed-width line with cores for a few truck shares
        from matplotlib.legend_handler import HandlerTuple
        kw = 8.0
        shares = (0.4, 0.2, 0.1)
        comp = [(Line2D([], [], color=tc["car"], lw=kw, solid_capstyle="butt"),
                 Line2D([], [], color=tc["truck"], lw=kw * sh, solid_capstyle="butt"))
                for sh in shares]
        leg3 = ax.legend(handles=comp, labels=[f"{sh:.0%} ciężarowych" for sh in shares],
                         handler_map={tuple: HandlerTuple(ndivide=1)},
                         loc="lower left", bbox_to_anchor=(0.01, 0.13), frameon=False,
                         fontsize=9.5, labelcolor=t["text2"], handlelength=3.4,
                         title="Udział samochodów ciężarowych", title_fontsize=11,
                         borderaxespad=0.2, alignment="left", labelspacing=0.9)
        leg3.get_title().set_color(t["text"])
        ax.add_artist(leg3)
    if mode == "truckshare":
        wh = [Line2D([], [], color=t["text2"], lw=width(v), solid_capstyle="butt", label=fmt(v))
              for v in (100_000, 30_000, 5_000)]
        leg4 = ax.legend(handles=wh, loc="lower left", bbox_to_anchor=(0.01, 0.16),
                         frameon=False, fontsize=9.5, labelcolor=t["text2"],
                         title="SDRR [pojazdy/dobę]", title_fontsize=11, handlelength=3.4,
                         borderaxespad=0.2, alignment="left")
        leg4.get_title().set_color(t["text"])
        ax.add_artist(leg4)
    # context legend (next to the class legend, over Czechia): one entry for every road
    # without data, dotted GPR sections without a result (only if any), cities as a blob
    ctx_h = [Line2D([], [], color=t["ctx"], lw=1.2, solid_capstyle="butt",
                    label="drogi bez danych\n(głównie odcinki w miastach)")]
    if len(nodata):
        ctx_h.append(Line2D([], [], color=t["ctx"], lw=1.2, linestyle=(0, (1, 1.2)),
                            label=f"odcinki bez pomiaru w {config.YEAR}"))
    handler_map = {}
    if cities is not None and len(cities):
        from matplotlib.patches import Patch
        city_h = Patch(facecolor=t["city"], edgecolor="none", label="miasta na prawach powiatu")
        ctx_h.append(city_h)
        handler_map[city_h] = BlobHandler()
    leg2 = ax.legend(handles=ctx_h, loc="lower left", bbox_to_anchor=(0.175, 0.035),
                     frameon=False, fontsize=9, labelcolor=t["text2"], handlelength=3.4,
                     borderaxespad=0.2, handler_map=handler_map, labelspacing=0.9)
    fig.text(0.025, 0.015, f"Dane: GDDKiA GPR {config.YEAR}, BDOT10k (GUGiK), OpenStreetMap · "
             f"© {config.AUTHOR}, autorzy OpenStreetMap", fontsize=7.5, color=t["text2"], ha="left")
    out = config.OUT / (f"cartogram_{config.YEAR}{'_dkdw' if dwsec is not None else ''}"
                        f"{'_' + mode if mode else ''}{RAMP_TAG}_{theme}.png")
    fig.savefig(out, facecolor=t["bg"])
    plt.close(fig)
    print(f"saved {out}")


def main():
    import matplotlib.patheffects  # noqa: F401
    use_font()
    sec = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    ctx = gpd.read_file(config.NETWORK_GPKG, layer="skdr_unmeasured")
    cities = None
    try:
        cities = gpd.read_file(config.OSM_GPKG, layer="cities")
    except Exception:
        pass
    try:
        dw = gpd.read_file(config.NETWORK_GPKG, layer="regional_roads")
        dw["geometry"] = dw.geometry.simplify(20)
    except Exception:
        dw = None
    adm = gpd.read_file(config.BOUNDARY_SHP).to_crs(2180)
    voiv = adm[adm.RODZAJ == "województwo"].dissolve(by="NAZWA").reset_index()
    voiv["geometry"] = voiv.buffer(200).buffer(-200).simplify(100)   # close sheet slivers
    country = gpd.GeoDataFrame(geometry=[voiv.unary_union.buffer(200).buffer(-200)], crs=2180)
    if config.LAND_SHP.exists():
        # the admin outline includes territorial waters (Gulf of Gdańsk, lagoons): keep its
        # land borders but cut the coast with a land-only outline (Natural Earth)
        ne = gpd.read_file(config.LAND_SHP)
        ne = ne[ne["ADM0_A3"] == "POL"].to_crs(2180)
        land = ne.unary_union.buffer(2000).intersection(country.unary_union)
        coast_cut = country.unary_union.difference(ne.unary_union.buffer(300))
        country = gpd.GeoDataFrame(geometry=[land.difference(coast_cut)], crs=2180)
    if cities is not None and len(cities):
        # OSM city boundaries of Gdańsk / Gdynia / Szczecin … run into the sea: land only
        cities = gpd.clip(cities.to_crs(2180), country)
    # --dw: national + regional sections (GPR_NET=dw output) on one map, written as
    # cartogram_<year>_dkdw_*.png; without it the national-only map
    dwsec = None
    if "--dw" in sys.argv and config.DW_NETWORK_GPKG.exists():
        dwsec = gpd.read_file(config.DW_NETWORK_GPKG, layer="sections")
        dwsec = dwsec[dwsec.sdrr_total.notna()]
        print(f"regional sections: {len(dwsec)}")
    for d in (sec, dwsec):
        if d is not None:   # trucks = samochody ciężarowe bez + z przyczepą
            d["trucks"] = d.sdrr_ciezarowe_bez.fillna(0) + d.sdrr_ciezarowe_z.fillna(0)
    modes = ["trucks", "truckshare"] if "--trucks" in sys.argv else [None]
    if "--ramp" in sys.argv:   # a candidate share ramp only
        global TRUCK_SHARE_RAMP, RAMP_TAG
        name = sys.argv[sys.argv.index("--ramp") + 1]
        TRUCK_SHARE_RAMP, RAMP_TAG, modes = TRUCK_SHARE_VARIANTS[name], f"_{name}", ["truckshare"]
    for mode in modes:
        for theme in THEMES:
            render(theme, sec, ctx, dw, voiv, country, cities, dwsec, mode)


if __name__ == "__main__":
    main()
