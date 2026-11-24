"""Small helpers shared by the pipeline steps."""
import re

_EURO = re.compile(r"^E\d+$")


def skdr_tokens(numer_drog):
    """Road numbers carried by a BDOT10k SKDR feature.

    NUMER_DROG mixes separators and case: 'E77|S7', 'E77;S7', '75, 28', 's19'.
    Returns a frozenset like {'S7'} or {'75', '28'}; European numbers are dropped.
    """
    if numer_drog is None or (isinstance(numer_drog, float) and numer_drog != numer_drog):
        return frozenset()
    out = set()
    for tok in re.split(r"[|;,\s]+", str(numer_drog).upper()):
        if not tok or _EURO.match(tok):
            continue
        m = re.match(r"^(A|S|DK)?0*(\d+)[A-Z]?$", tok)
        if m:
            prefix = "" if m.group(1) in (None, "DK") else m.group(1)
            out.add(f"{prefix}{int(m.group(2))}")
    return frozenset(out)


def system_base(system):
    """GPR chainage system → (road, number): 'S7j' → ('S7', '7'), '94g' → ('94', '94')."""
    m = re.match(r"^([AS]?)(\d+)", str(system).strip())
    if not m:
        return None, None
    num = str(int(m.group(2)))
    return f"{m.group(1)}{num}", num


def road_class(road):
    """'A2' → 'A', 'S7' → 'S', '94' → 'DK'."""
    return road[0] if road and road[0] in "AS" else "DK"


def to_float(x):
    if x is None:
        return float("nan")
    try:
        return float(str(x).replace(",", ".").strip())
    except ValueError:
        return float("nan")
