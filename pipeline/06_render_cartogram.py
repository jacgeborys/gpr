"""
06_render_cartogram.py — static traffic flow map in light and dark themes:
line width ∝ SDRR, colour continuous along the SDRR class ramp (config.SDRR_BREAKS /
SDRR_COLORS_*: each class colour at its class middle, as in the legend), font Bahnschrift.

Reads : output/traffic_network_2025.gpkg, config.BOUNDARY_SHP
Writes: output/cartogram_2025_light.png, output/cartogram_2025_dark.png
"""
import geopandas as gpd
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


def use_font():
    try:
        font_manager.fontManager.addfont(FONT_FILE)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT_FILE).get_name()
    except (OSError, RuntimeError):
        print(f"font {FONT_FILE} not found, using the default")


def smooth_color(v, ramp):
    """Continuous colour: each class colour sits at its class middle (the legend swatch value)
    and colours blend linearly in between, so local differences inside a class show."""
    from matplotlib.colors import to_rgb
    b = [0] + config.SDRR_BREAKS + [SDRR_MAX]
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


def render(theme, sec, ctx, dw, voiv, country, cities=None):
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
    data = sec[sec.sdrr_total.notna()].sort_values("sdrr_total")
    lines, ws, cs = [], [], []
    for g, v in zip(data.geometry, data.sdrr_total):
        for s in segs(g):
            lines.append(s)
            ws.append(width(v))
            cs.append(smooth_color(v, t["ramp"]))
    ax.add_collection(LineCollection(lines, linewidths=ws, colors=cs, capstyle="round",
                                     joinstyle="round", zorder=4))

    pts = gpd.GeoSeries(gpd.points_from_xy([c[0] for c in CITIES.values()],
                                           [c[1] for c in CITIES.values()]), crs=4326).to_crs(2180)
    for name, p in zip(CITIES, pts):
        ax.plot(p.x, p.y, "o", ms=3, color=t["text"], zorder=5)
        ax.annotate(name, (p.x, p.y), xytext=(5, 4), textcoords="offset points", fontsize=9,
                    color=t["text"], zorder=6, fontweight="medium",
                    path_effects=[matplotlib.patheffects.withStroke(linewidth=2.5,
                                                                    foreground=t["bg"])])

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.025, 0.965, f"Ruch na drogach krajowych {config.YEAR}", fontsize=24,
             color=t["text"], va="top")
    fig.text(0.025, 0.922, "Średni dobowy ruch roczny (SDRR), pojazdy/dobę · Generalny Pomiar Ruchu "
             f"GDDKiA {config.YEAR}", fontsize=11, color=t["text2"], va="top")

    # class legend: colour + width of each class (width at the class middle), flat ends
    b = [0] + config.SDRR_BREAKS + [SDRR_MAX]
    mids = [(lo + hi) / 2 for lo, hi in zip(b[:-1], b[1:])]
    handles = [Line2D([], [], color=c, lw=width(m), solid_capstyle="butt", label=lab)
               for c, m, lab in zip(t["ramp"], mids, class_labels())][::-1]
    leg = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.01, 0.035),
                    frameon=False, fontsize=9.5, labelcolor=t["text2"],
                    title="SDRR [pojazdy/dobę]", title_fontsize=11, handlelength=3.4,
                    borderaxespad=0.2, alignment="left")
    leg.get_title().set_color(t["text"])
    ax.add_artist(leg)
    # context legend (next to the class legend, over Czechia)
    ctx_h = [Line2D([], [], color=t["ctx"], lw=1.4, solid_capstyle="butt",
                    label="drogi krajowe bez pomiaru GPR\n(głównie odcinki w miastach)")]
    if dw is not None and len(dw):
        ctx_h.append(Line2D([], [], color=t["ctx"], lw=0.5, solid_capstyle="butt",
                            label="drogi wojewódzkie (bez danych o ruchu)"))
    if cities is not None and len(cities):
        from matplotlib.patches import Patch
        ctx_h.append(Patch(facecolor=t["city"], edgecolor="none",
                           label="miasta na prawach powiatu"))
    leg2 = ax.legend(handles=ctx_h, loc="lower left", bbox_to_anchor=(0.175, 0.035),
                     frameon=False, fontsize=9, labelcolor=t["text2"], handlelength=3.4,
                     borderaxespad=0.2)
    fig.text(0.025, 0.015, f"Dane: GDDKiA GPR {config.YEAR}, BDOT10k (GUGiK), © autorzy OpenStreetMap · "
             "geometria odcinków: kilometraż GPR na sieci BDOT10k uzupełnionej OSM", fontsize=7.5, color=t["text2"], ha="left")
    out = config.OUT / f"cartogram_{config.YEAR}_{theme}.png"
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
    for theme in THEMES:
        render(theme, sec, ctx, dw, voiv, country, cities)


if __name__ == "__main__":
    main()
