<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" nodataColor="" classificationMin="-0.005" classificationMax="0.005">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" classificationMode="1" clip="0" minimumValue="-0.005" maximumValue="0.005" labelPrecision="4">
          <item value="-0.005" color="#8c510a" label="&lt;= -0.0050 NDVI/month (browning)" alpha="255"/>
          <item value="-0.0025" color="#d8b365" label="-0.0025" alpha="255"/>
          <item value="0" color="#f6f6f6" label="0 (stable)" alpha="255"/>
          <item value="0.0025" color="#a6d96a" label="+0.0025" alpha="255"/>
          <item value="0.005" color="#1a9850" label="&gt;= +0.0050 NDVI/month (greening)" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
