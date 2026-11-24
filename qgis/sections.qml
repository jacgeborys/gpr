<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="Symbology">
 <renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="1" forceraster="0">
  <symbols>
   <symbol type="line" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
    <layer class="SimpleLine" enabled="1" pass="0" locked="0">
     <Option type="Map">
      <Option name="capstyle" value="round" type="QString"/>
      <Option name="joinstyle" value="round" type="QString"/>
      <Option name="line_color" value="37,106,191,255" type="QString"/>
      <Option name="line_style" value="solid" type="QString"/>
      <Option name="line_width" value="0.5" type="QString"/>
      <Option name="line_width_unit" value="MM" type="QString"/>
     </Option>
     <data_defined_properties><Option type="Map">
      <Option name="name" value="" type="QString"/>
      <Option name="properties" type="Map"><Option name="outlineWidth" type="Map"><Option name="active" value="true" type="bool"/><Option name="expression" value="coalesce(scale_linear(&quot;sdrr_total&quot;,0,120000,0.15,3.4),0.2)" type="QString"/><Option name="type" value="3" type="int"/></Option><Option name="outlineColor" type="Map"><Option name="active" value="true" type="bool"/><Option name="expression" value="CASE WHEN &quot;sdrr_total&quot; IS NULL THEN '#a3a29b' ELSE ramp_color(create_ramp(map(0,'#9ec5f4',0.2,'#6da7ec',0.4,'#3987e5',0.6,'#256abf',0.8,'#184f95',1,'#0d366b')),scale_linear(&quot;sdrr_total&quot;,0,120000,0,1)) END" type="QString"/><Option name="type" value="3" type="int"/></Option></Option>
      <Option name="type" value="collection" type="QString"/>
     </Option></data_defined_properties>
    </layer>
   </symbol>
  </symbols>
  <orderby><orderByClause asc="1" nullsFirst="1">&quot;sdrr_total&quot;</orderByClause></orderby>
 </renderer-v2>
</qgis>
