<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" nodataColor="" classificationMin="0" classificationMax="100">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" classificationMode="1" clip="0" minimumValue="0" maximumValue="100" labelPrecision="0">
          <item value="0" color="#d7191c" label="0 (worst month on record)" alpha="255"/>
          <item value="25" color="#fdae61" label="25" alpha="255"/>
          <item value="35" color="#ffffbf" label="35 (drought threshold)" alpha="255"/>
          <item value="75" color="#a6d96a" label="75" alpha="255"/>
          <item value="100" color="#1a9641" label="100 (best month on record)" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
