"""
07_style_qgis.py — write QGIS styles (.qml) and embed them as default styles in the
GeoPackage, so dragging traffic_network_2025.gpkg into QGIS shows the flow map at once.

  sections / links : width ∝ SDRR (mm), colour by SDRR class (as the PNG), drawn low → high;
                     no-count links in thin grey
  skdr_unmeasured  : thin grey context
  skdr_not_operational : dashed grey

Writes: qgis/*.qml and the 'layer_styles' table inside output/traffic_network_2025.gpkg
"""
import datetime
import sqlite3

import config

QGIS_DIR = config.ROOT / "qgis"
MAX = 120000
WIDTH = f'coalesce(scale_linear("sdrr_total",0,{MAX},0.15,3.4),0.2)'
# same SDRR classes and colours as the PNG map (config.SDRR_BREAKS / SDRR_COLORS_LIGHT)
COLOR = ("CASE WHEN \"sdrr_total\" IS NULL THEN '#a3a29b' "
         + " ".join(f"WHEN \"sdrr_total\" < {b} THEN '{c}'"
                    for b, c in zip(config.SDRR_BREAKS, config.SDRR_COLORS_LIGHT))
         + f" ELSE '{config.SDRR_COLORS_LIGHT[-1]}' END")


def esc(x):
    return x.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def line_qml(color, width_mm, dash=False, dd_width=None, dd_color=None, order_by=None):
    def dd(name, expr):
        return (f'<Option name="{name}" type="Map"><Option name="active" value="true" type="bool"/>'
                f'<Option name="expression" value="{esc(expr)}" type="QString"/>'
                f'<Option name="type" value="3" type="int"/></Option>')
    props = (dd("outlineWidth", dd_width) if dd_width else "") + \
            (dd("outlineColor", dd_color) if dd_color else "")
    order = (f'<orderby><orderByClause asc="1" nullsFirst="1">{esc(order_by)}</orderByClause></orderby>'
             if order_by else "")
    return f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="Symbology">
 <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="{1 if order_by else 0}" forceraster="0">
  <symbols>
   <symbol type="line" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
    <layer class="SimpleLine" enabled="1" pass="0" locked="0">
     <Option type="Map">
      <Option name="capstyle" value="round" type="QString"/>
      <Option name="joinstyle" value="round" type="QString"/>
      <Option name="line_color" value="{color}" type="QString"/>
      <Option name="line_style" value="{'dash' if dash else 'solid'}" type="QString"/>
      <Option name="line_width" value="{width_mm}" type="QString"/>
      <Option name="line_width_unit" value="MM" type="QString"/>
     </Option>
     <data_defined_properties><Option type="Map">
      <Option name="name" value="" type="QString"/>
      <Option name="properties" type="Map">{props}</Option>
      <Option name="type" value="collection" type="QString"/>
     </Option></data_defined_properties>
    </layer>
   </symbol>
  </symbols>
  {order}
 </renderer-v2>
</qgis>
"""


STYLES = {
    "sections": line_qml("37,106,191,255", 0.5, dd_width=WIDTH, dd_color=COLOR, order_by='"sdrr_total"'),
    "links": line_qml("37,106,191,255", 0.5, dd_width=WIDTH, dd_color=COLOR, order_by='"sdrr_total"'),
    "skdr_unmeasured": line_qml("201,200,193,255", 0.15),
    "skdr_not_operational": line_qml("82,81,78,255", 0.25, dash=True),
}


def main():
    QGIS_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(config.NETWORK_GPKG)
    layers = {r[0] for r in con.execute("SELECT table_name FROM gpkg_contents")}
    con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT, f_table_schema TEXT,
        f_table_name TEXT, f_geometry_column TEXT, styleName TEXT, styleQML TEXT,
        styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT, ui TEXT,
        update_time DATETIME)""")
    if "layer_styles" not in layers:
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, last_change) "
                    "VALUES ('layer_styles', 'attributes', 'layer_styles', ?)",
                    (datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),))
    con.execute("DELETE FROM layer_styles")
    for name, qml in STYLES.items():
        (QGIS_DIR / f"{name}.qml").write_text(qml, encoding="utf-8")
        if name not in layers:
            continue
        geom_col = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
                               (name,)).fetchone()[0]
        con.execute("INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, "
                    "f_geometry_column, styleName, styleQML, styleSLD, useAsDefault, description, "
                    "owner, ui, update_time) VALUES ('', '', ?, ?, ?, ?, '', 1, ?, '', '', "
                    "datetime('now'))", (name, geom_col, name, qml, "gpr pipeline default"))
    con.commit()
    con.close()
    print(f"wrote {len(STYLES)} .qml files to {QGIS_DIR} and default styles into "
          f"{config.NETWORK_GPKG.name}")


if __name__ == "__main__":
    main()
