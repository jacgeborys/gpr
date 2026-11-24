"""
06_render_cartogram.py — static traffic flow map (width ∝ SDRR) in light and dark themes.

Reads : output/traffic_network_2025.gpkg, config.BOUNDARY_SHP
Writes: output/cartogram_2025_light.png, output/cartogram_2025_dark.png
"""
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import config  # noqa: E402

# single-hue sequential blue ramp (steps 200 → 700); dark theme uses lighter top end
RAMP_LIGHT = ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
RAMP_DARK = ["#184f95", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef", "#cde2fb"]
THEMES = {
    "light": dict(bg="#fcfcfb", land="#f3f2ef", border="#d6d5cf", ctx="#c9c8c1",
                  text="#0b0b0b", text2="#52514e", ramp=RAMP_LIGHT),
    "dark": dict(bg="#1a1a19", land="#232322", border="#3a3a37", ctx="#4a4a46",
                 text="#f0efec", text2="#c3c2b7", ramp=RAMP_DARK),
}
SDRR_MAX = 120_000           # width/colour saturate here (a handful of urban A4/S8 links exceed it)
W_MIN, W_MAX = 0.35, 9.0     # line width in points
CITIES = {"Warszawa": (21.01, 52.23), "Kraków": (19.94, 50.06), "Łódź": (19.46, 51.76),
          "Wrocław": (17.03, 51.11), "Poznań": (16.93, 52.41), "Gdańsk": (18.65, 54.35),
          "Szczecin": (14.55, 53.43), "Katowice": (19.02, 50.26), "Lublin": (22.57, 51.25),
          "Białystok": (23.16, 53.13), "Rzeszów": (22.00, 50.04), "Bydgoszcz": (18.01, 53.12),
          "Olsztyn": (20.49, 53.78), "Kielce": (20.63, 50.87), "Zielona Góra": (15.51, 51.94)}


def width(v):
    return W_MIN + (W_MAX - W_MIN) * np.clip(v / SDRR_MAX, 0, 1)


def segs(geom):
    parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
    return [np.asarray(p.coords)[:, :2] for p in parts]


def render(theme, sec, ctx, notop, voiv, country):
    t = THEMES[theme]
    cmap = LinearSegmentedColormap.from_list("seq", t["ramp"])
    norm = Normalize(0, SDRR_MAX)
    fig, ax = plt.subplots(figsize=(13, 12.4), dpi=200)
    fig.patch.set_facecolor(t["bg"])
    ax.set_facecolor(t["bg"])
    country.plot(ax=ax, color=t["land"], edgecolor="none")
    voiv.boundary.plot(ax=ax, color=t["border"], linewidth=0.5)
    country.boundary.plot(ax=ax, color=t["border"], linewidth=0.9)
    ax.add_collection(LineCollection([s for g in ctx.geometry for s in segs(g)],
                                     colors=t["ctx"], linewidths=0.35, zorder=2))
    if notop is not None and len(notop):
        ax.add_collection(LineCollection([s for g in notop.geometry for s in segs(g)],
                                         colors=t["text2"], linewidths=0.6, linestyles=(0, (2, 2)),
                                         zorder=2))
    nodata = sec[sec.sdrr_total.isna()]
    ax.add_collection(LineCollection([s for g in nodata.geometry for s in segs(g)],
                                     colors=t["text2"], linewidths=0.8, linestyles=(0, (1, 1.5)),
                                     zorder=3))
    data = sec[sec.sdrr_total.notna()].sort_values("sdrr_total")
    lines, ws, cs = [], [], []
    for g, v in zip(data.geometry, data.sdrr_total):
        for s in segs(g):
            lines.append(s)
            ws.append(width(v))
            cs.append(cmap(norm(v)))
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

    minx, miny, maxx, maxy = country.total_bounds
    ax.set_xlim(minx - 15_000, maxx + 15_000)
    ax.set_ylim(miny - 15_000, maxy + 15_000)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.text(0.06, 0.955, f"Ruch na drogach krajowych {config.YEAR}", fontsize=20,
             fontweight="bold", color=t["text"])
    fig.text(0.06, 0.93, "Średni dobowy ruch roczny (SDRR), pojazdy/dobę · Generalny Pomiar Ruchu "
             f"GDDKiA {config.YEAR}", fontsize=11, color=t["text2"])

    # width + colour legend (shared encoding)
    handles = [Line2D([], [], color=cmap(norm(v)), lw=width(v), solid_capstyle="round",
                      label=f"{v:,.0f}".replace(",", " ")) for v in (5_000, 20_000, 50_000, 100_000)]
    handles += [Line2D([], [], color=t["text2"], lw=0.8, ls=(0, (1, 1.5)),
                       label="brak wyniku (oddane XII 2025 / pomiar 2026)"),
                Line2D([], [], color=t["ctx"], lw=0.8, label="pozostałe drogi krajowe (bez pomiaru)")]
    if notop is not None and len(notop):
        handles.append(Line2D([], [], color=t["text2"], lw=0.8, ls=(0, (2, 2)),
                              label="w budowie (BDOT10k)"))
    leg = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 0.02), frameon=False, fontsize=9,
                    labelcolor=t["text2"], title="SDRR [poj./dobę]", title_fontsize=10,
                    handlelength=3.2, borderaxespad=0.2)
    leg.get_title().set_color(t["text"])
    fig.text(0.94, 0.03, "Dane: GDDKiA GPR 2025, BDOT10k (GUGiK) · geometria odcinków: "
             "kilometraż GPR na sieci BDOT10k", fontsize=7.5, color=t["text2"], ha="right")
    out = config.OUT / f"cartogram_{config.YEAR}_{theme}.png"
    fig.savefig(out, facecolor=t["bg"], bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"saved {out}")


def main():
    import matplotlib.patheffects  # noqa: F401
    sec = gpd.read_file(config.NETWORK_GPKG, layer="sections")
    ctx = gpd.read_file(config.NETWORK_GPKG, layer="skdr_unmeasured")
    try:
        notop = gpd.read_file(config.NETWORK_GPKG, layer="skdr_not_operational")
    except Exception:
        notop = None
    adm = gpd.read_file(config.BOUNDARY_SHP).to_crs(2180)
    voiv = adm[adm.RODZAJ == "województwo"].dissolve(by="NAZWA").reset_index()
    voiv["geometry"] = voiv.buffer(200).buffer(-200).simplify(100)   # close sheet slivers
    country = gpd.GeoDataFrame(geometry=[voiv.unary_union.buffer(200).buffer(-200)], crs=2180)
    for theme in THEMES:
        render(theme, sec, ctx, notop, voiv, country)


if __name__ == "__main__":
    main()
