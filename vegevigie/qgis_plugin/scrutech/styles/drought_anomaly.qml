<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" nodataColor="" classificationMin="-2" classificationMax="2">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" classificationMode="1" clip="0" minimumValue="-2" maximumValue="2" labelPrecision="1">
          <item value="-2" color="#ca0020" label="&lt;= -2.0 z (severe stress)" alpha="255"/>
          <item value="-1" color="#f4a582" label="-1.0 z (stress)" alpha="255"/>
          <item value="0" color="#f7f7f7" label="0 (normal)" alpha="255"/>
          <item value="1" color="#92c5de" label="+1.0 z" alpha="255"/>
          <item value="2" color="#0571b0" label="&gt;= +2.0 z (wetter than normal)" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
