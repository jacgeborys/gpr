"""
01_parse_gpr2010_dw.py — GPR 2010 regional roads (drogi wojewódzkie) from GDDKiA's table
0116_SDR_drwoj_w_pkt_pomiarowych_w_2010_roku.pdf (number, road, km from–to, length, name, SDR
of motor vehicles and 7 classes; no counting-point coordinates).

The PDF text needs care: the bold voivodeship heading is printed over some rows (its chars are
dropped by font), and long section names run into the SDR column. Rows are therefore read
character by character: the numbers are right-aligned on a fixed grid (right edges in COLS_X1),
so each number is peeled off from its column's right edge; whatever else lies left of the SDR
column is the name.

Writes: output/gpr2010_dw_sections.csv
"""
import re

import numpy as np
import pandas as pd
import pdfplumber

import config

SRC = config.RAW / "0116_SDR_drwoj_w_pkt_pomiarowych_w_2010_roku.pdf"
OUT = config.OUT / "gpr2010_dw_sections.csv"
# right edges (pt) of the number columns: SDR total, motorcycles, cars, vans, lorries w/o
# trailer, lorries with trailer, buses, tractors
COLS_X1 = [326.8, 353.9, 388.3, 420.4, 453.8, 483.9, 513.3, 540.7]
NUM_COLS = ["sdrr_total", "sdrr_motocykle", "sdrr_sam_osobowe", "sdrr_lekkie_ciezarowe",
            "sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy", "sdrr_ciagniki"]
HEAD = re.compile(r"^(\d{5}) (\d{3}[a-z]?) (\d+,\d+) (\d+,\d+) (\d+,\d+) ?")


def digit_runs(chars):
    """Runs of touching digit chars (gap < 0.5 pt), other chars ignored: [(x1, text)]."""
    ds = sorted((c for c in chars if c["text"].isdigit()), key=lambda c: c["x0"])
    runs, cur = [], []
    for c in ds:
        if cur and c["x0"] - cur[-1]["x1"] > 0.5:
            runs.append(cur)
            cur = []
        cur.append(c)
    if cur:
        runs.append(cur)
    return [(r[-1]["x1"], "".join(c["text"] for c in r), r) for r in runs]


def numbers(ch):
    """Values of the 8 number columns of one row (None where empty) and the chars used. The
    total's run may carry digits of an overflowing name in front: it is cut to the sum of the
    classes when they add up to one of its suffixes."""
    vals, used = [None] * len(COLS_X1), set()
    for x1, txt, r in digit_runs([c for c in ch if c["x0"] > COLS_X1[0] - 30]):
        k = int(np.argmin([abs(x1 - e) for e in COLS_X1]))
        if abs(x1 - COLS_X1[k]) <= 3.5 and vals[k] is None:
            vals[k] = txt
            used |= {id(c) for c in r}
    cls = vals[1:]
    if vals[0] is not None and all(v is not None for v in cls):
        tot = sum(int(v) for v in cls)
        for i in range(len(vals[0])):
            if abs(int(vals[0][i:]) - tot) <= 2:
                vals[0] = vals[0][i:]
                break
        else:   # name digits glued to the total beyond repair: the classes' sum
            vals[0] = str(tot)
    return [int(v) if v is not None else None for v in vals], used


def rows_of(page):
    chars = [c for c in page.chars if "Bold" not in (c.get("fontname") or "")]
    by_top = {}
    for c in chars:
        by_top.setdefault(round(c["top"]), []).append(c)
    # merge neighbouring tops (±1 pt) into one row
    tops = sorted(by_top)
    groups, cur = [], []
    for t in tops:
        if cur and t - cur[-1] > 1:
            groups.append(cur)
            cur = []
        cur.append(t)
    if cur:
        groups.append(cur)
    for g in groups:
        yield sorted((c for t in g for c in by_top[t]), key=lambda c: c["x0"])


def main():
    out = []
    with pdfplumber.open(SRC) as pdf:
        for page in pdf.pages:
            for ch in rows_of(page):
                # columns 1–5 (number, road, km, km, length) lie left of x 160; a gap > 1 pt
                # between chars is a space
                text, prev = "", None
                for c in ch:
                    if c["x1"] >= 160:
                        break
                    if prev is not None and c["x0"] - prev > 1:
                        text += " "
                    text += c["text"]
                    prev = c["x1"]
                m = HEAD.match(re.sub(r"\s+", " ", text).strip() + " ")
                if not m:
                    # a wrapped name: the numbers sit on the next line; fill the row above
                    if out and out[-1]["sdrr_total"] is None and not text.strip():
                        vals, used = numbers(ch)
                        if vals[0] is not None:
                            out[-1].update(zip(NUM_COLS, vals))
                            more = "".join(c["text"] for c in ch if 160 < c["x0"] < COLS_X1[0] - 30)
                            out[-1]["nazwa_odcinka"] = re.sub(
                                r"\s+", " ", out[-1]["nazwa_odcinka"] + " " + more).strip()
                    continue
                vals, used = numbers(ch)
                tot_digits = len(str(vals[0])) if vals[0] is not None else 0
                # name: chars right of the head, left of the total column, minus the total's
                # digits (the last tot_digits digit chars before the total's right edge)
                name = "".join(c["text"] for c in ch if 160 < c["x0"] < COLS_X1[0] + 1
                               and not (id(c) in used and c["text"].isdigit()
                                        and c["x0"] > COLS_X1[0] - 3.2 * tot_digits - 0.5))
                name = name.strip()
                r = dict(numer_odcinka=m.group(1), nr_drogi=m.group(2),
                         pik_pocz=float(m.group(3).replace(",", ".")),
                         pik_konc=float(m.group(4).replace(",", ".")),
                         dlugosc_km=float(m.group(5).replace(",", ".")),
                         nazwa_odcinka=re.sub(r"\s+", " ", name))
                r.update(zip(NUM_COLS, vals))
                out.append(r)
    s = pd.DataFrame(out).drop_duplicates("numer_odcinka")
    s["system"] = s["nr_drogi"]
    s["road"] = s["nr_drogi"].str.extract(r"(\d+)")[0].astype(int).astype(str)
    s["sdrr_heavy"] = s[["sdrr_ciezarowe_bez", "sdrr_ciezarowe_z", "sdrr_autobusy",
                         "sdrr_ciagniki"]].sum(axis=1, min_count=1)
    s["heavy_share"] = (s["sdrr_heavy"] / s["sdrr_total"]).round(3)
    s["status"] = np.where(s["sdrr_total"].notna(), "measured", "no_data")
    # check: the classes add up to the total (a misread digit breaks the sum)
    parts = s[NUM_COLS[1:]].sum(axis=1)
    off = (parts - s.sdrr_total).abs() > 2
    print(f"GPR 2010 regional sections: {len(s)} on {s.road.nunique()} roads, "
          f"{s.dlugosc_km.sum():,.0f} km; SDR read: {s.sdrr_total.notna().sum()}; "
          f"classes not adding up to the total: {off.sum()}")
    if off.any():
        print(s.loc[off, ["numer_odcinka", "nazwa_odcinka"] + NUM_COLS].head(10).to_string())
    s.to_csv(OUT, index=False, encoding="utf-8")
    print(f"saved {OUT.name}")


if __name__ == "__main__":
    main()
