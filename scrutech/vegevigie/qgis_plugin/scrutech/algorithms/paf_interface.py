"""PAF algorithm: forest/built-up interface (Wildland-Urban Interface).

Pick a forest layer and a built-up layer, set the contact distance (default 50 m,
the French OLD débroussaillement footprint), hit Run — ScruTech computes the
frontier line where forest meets buildings and the contact band to defend, and
loads both into the project.

Pure **native QGIS geometry** (QgsGeometry: reproject, dissolve, buffer, boundary,
intersection) — no GeoPandas, no datacube stack, no internet. Distance/area maths
run in the chosen metric CRS (Lambert-93 by default); inputs in any CRS are
reprojected on the fly.
"""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeatureSource,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication, QVariant

from . import _qgis_compat as _compat

# Buffer smoothness (segments per quarter-circle). 8 is QGIS's default trade-off.
_BUFFER_SEGMENTS = 8


class InterfaceHabitatForetAlgorithm(QgsProcessingAlgorithm):
    """Forest/built-up interface (WUI): frontier line + contact band — native QGIS."""

    FOREST = "FOREST"
    BATI = "BATI"
    CONTACT_M = "CONTACT_M"
    METRIC_CRS = "METRIC_CRS"
    LINE_OUTPUT = "LINE_OUTPUT"
    ZONE_OUTPUT = "ZONE_OUTPUT"

    def name(self) -> str:
        return "interface_habitat_foret"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Interface habitat-forêt (WUI)")

    def group(self) -> str:
        return self.tr("PAF — forest fire")

    def groupId(self) -> str:  # noqa: N802
        return "paf"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Compute the Wildland-Urban Interface between a forest layer and a built-up "
            "layer: the frontier line (forest edge within the contact distance of a "
            "building) and the contact band (forest within that distance — the "
            "débroussaillement / defence zone). Distance and area maths run in the chosen "
            "metric CRS (Lambert-93 by default). Frontier length and band area are "
            "reported in the log. Native QGIS geometry only — no extra dependencies, no "
            "internet."
        )

    def createInstance(self) -> InterfaceHabitatForetAlgorithm:  # noqa: N802
        return InterfaceHabitatForetAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("paf")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.FOREST, self.tr("Forest zones"), [_compat.SOURCE_VECTOR_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BATI, self.tr("Built-up zones"), [_compat.SOURCE_VECTOR_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CONTACT_M,
                self.tr("Contact distance (m) — OLD débroussaillement = 50"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=50.0,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.METRIC_CRS,
                self.tr("Metric CRS for distance/area maths"),
                defaultValue="EPSG:2154",
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.LINE_OUTPUT,
                self.tr("Interface line (frontier)"),
                _compat.SOURCE_VECTOR_LINE,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ZONE_OUTPUT,
                self.tr("Interface zone (contact band)"),
                _compat.SOURCE_VECTOR_POLYGON,
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        contact_m = self.parameterAsDouble(parameters, self.CONTACT_M, context)
        metric_crs = self.parameterAsCrs(parameters, self.METRIC_CRS, context)
        if not metric_crs.isValid() or metric_crs.isGeographic():
            raise QgsProcessingException(
                self.tr(
                    "Metric CRS must be a projected (metre-based) CRS, e.g. EPSG:2154 — "
                    "distances in degrees are meaningless."
                )
            )

        forest_src = self.parameterAsSource(parameters, self.FOREST, context)
        bati_src = self.parameterAsSource(parameters, self.BATI, context)
        if forest_src is None or bati_src is None:
            raise QgsProcessingException(self.tr("Forest and built-up layers are required."))

        forest_u = self._dissolve_to_crs(forest_src, metric_crs)
        bati_u = self._dissolve_to_crs(bati_src, metric_crs)
        if forest_u.isEmpty() or bati_u.isEmpty():
            raise QgsProcessingException(self.tr("Forest or built-up layer has no geometry."))

        reach = bati_u.buffer(contact_m, _BUFFER_SEGMENTS)
        zone = forest_u.intersection(reach)
        boundary = QgsGeometry(forest_u.constGet().boundary())
        line = boundary.intersection(reach)
        line.convertToMultiType()
        zone.convertToMultiType()

        length_m = line.length()
        area_ha = zone.area() / 10_000.0
        feedback.pushInfo(f"Frontier: {length_m / 1000:.2f} km | contact band: {area_ha:.1f} ha")
        if length_m == 0:
            feedback.reportError(
                self.tr(
                    "No interface found: forest and built-up never come within the "
                    "contact distance. Check the layers and the distance."
                )
            )

        line_id = self._write_sink(
            parameters,
            self.LINE_OUTPUT,
            context,
            metric_crs,
            _compat.WKB_MULTILINESTRING,
            QgsFields(),
            line,
        )
        zone_fields = QgsFields()
        zone_fields.append(QgsField("area_ha", QVariant.Double))
        zone_id = self._write_sink(
            parameters,
            self.ZONE_OUTPUT,
            context,
            metric_crs,
            _compat.WKB_MULTIPOLYGON,
            zone_fields,
            zone,
            attributes=[round(area_ha, 2)],
        )
        return {self.LINE_OUTPUT: line_id, self.ZONE_OUTPUT: zone_id}

    # --- helpers -------------------------------------------------------------
    def _dissolve_to_crs(self, source: QgsProcessingFeatureSource, crs) -> QgsGeometry:
        """Reproject every feature of ``source`` to ``crs`` and dissolve into one geometry."""
        xform = None
        if source.sourceCrs() != crs:
            xform = QgsCoordinateTransform(source.sourceCrs(), crs, QgsProject.instance())
        geoms: list[QgsGeometry] = []
        for feat in source.getFeatures():
            geom = feat.geometry()
            if geom.isEmpty():
                continue
            if xform is not None:
                geom = QgsGeometry(geom)
                geom.transform(xform)
            geoms.append(geom)
        if not geoms:
            return QgsGeometry()
        return QgsGeometry.unaryUnion(geoms)

    def _write_sink(
        self, parameters, name, context, crs, wkb_type, fields, geometry, attributes=None
    ) -> str:
        sink, dest_id = self.parameterAsSink(parameters, name, context, fields, wkb_type, crs)
        if sink is None:
            raise QgsProcessingException(self.tr(f"Could not create output '{name}'."))
        if not geometry.isEmpty():
            feat = QgsFeature(fields)
            feat.setGeometry(geometry)
            if attributes is not None:
                feat.setAttributes(attributes)
            sink.addFeature(feat, _compat.SINK_FAST_INSERT)
        return dest_id
