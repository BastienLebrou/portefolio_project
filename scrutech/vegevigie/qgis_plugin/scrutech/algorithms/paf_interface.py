"""PAFF algorithm: forest/built-up interface (Wildland-Urban Interface) from your own layers.

Pick a forest layer and a built-up layer, optionally a study area, set the contact distance
(default 50 m, the French OLD débroussaillement footprint), hit Run: ScruTech computes the
frontier line where forest meets buildings and the contact band to defend, and loads both
styled into the project.

Pure **native QGIS geometry** (QgsGeometry: reproject, repair, dissolve, buffer, boundary,
intersection): no GeoPandas, no datacube stack, no internet. Same geometry as the engine
(``vegevigie.interface.forest_bati_interface``): distances in a metric CRS, the study area
clips both layers, and the cut it makes through the forest is not counted as a frontier.
"""

from __future__ import annotations

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeatureSource,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterExtent,
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
    """Forest/built-up interface (WUI): frontier line + contact band, native QGIS."""

    FOREST = "FOREST"
    BATI = "BATI"
    EXTENT = "EXTENT"
    CONTACT_M = "CONTACT_M"
    METRIC_CRS = "METRIC_CRS"
    LINE_OUTPUT = "LINE_OUTPUT"
    ZONE_OUTPUT = "ZONE_OUTPUT"

    def name(self) -> str:
        return "interface_habitat_foret"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Interface habitat-forêt (couches en entrée)")

    def group(self) -> str:
        return self.tr("5 · Outils avancés (couches en entrée)")

    def groupId(self) -> str:  # noqa: N802
        return "avance"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Même calcul que « ③ Interface habitat-forêt » mais à partir de <b>vos "
            "propres couches</b> forêt et bâti (BD TOPO, BD Forêt, cadastre, relevés…). "
            "Fonctionne sans internet et sans le Python de ScruTech.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zones de forêt : une couche de polygones.<br>"
            "2. Zones bâties : une couche de polygones.<br>"
            "3. Zone d'étude (facultatif) : limite le calcul à une emprise. Conseillé avec des "
            "couches départementales, sinon le calcul peut durer plusieurs minutes.<br>"
            "4. Distance de contact : 50 m = obligation légale de débroussaillement (OLD) ; "
            "adaptez-la si un arrêté préfectoral fixe une autre valeur.<br>"
            "5. Exécuter.</p>"
            "<p><b>Résultat</b><br>La frontière habitat-forêt (ligne rouge) et la bande de "
            "débroussaillement (surface orange, avec sa superficie en ha). Le journal donne la "
            "longueur et la surface.</p>"
            "<p><b>Bon à savoir</b><br>Les couches peuvent être dans n'importe quel système de "
            "coordonnées : elles sont reprojetées en Lambert-93 (paramètre avancé) pour mesurer "
            "en mètres. Les géométries invalides sont réparées automatiquement.</p>"
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
                self.FOREST, self.tr("Zones de forêt"), [_compat.SOURCE_VECTOR_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.BATI, self.tr("Zones bâties"), [_compat.SOURCE_VECTOR_POLYGON]
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT,
                self.tr("Zone d'étude (facultatif : vide = couches entières)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CONTACT_M,
                self.tr("Distance de contact (m) : 50 = débroussaillement obligatoire"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=50.0,
                minValue=0.0,
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterCrs(
                    self.METRIC_CRS,
                    self.tr("Système de coordonnées métrique (calcul des distances)"),
                    defaultValue="EPSG:2154",
                )
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.LINE_OUTPUT,
                self.tr("Frontière habitat-forêt"),
                _compat.SOURCE_VECTOR_LINE,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.ZONE_OUTPUT,
                self.tr("Bande de débroussaillement"),
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
                    "Le système de coordonnées doit être métrique (en mètres), par exemple "
                    "EPSG:2154 : des distances en degrés n'ont pas de sens."
                )
            )

        forest_src = self.parameterAsSource(parameters, self.FOREST, context)
        bati_src = self.parameterAsSource(parameters, self.BATI, context)
        if forest_src is None or bati_src is None:
            raise QgsProcessingException(
                self.tr("Les couches de forêt et de bâti sont obligatoires.")
            )
        clip = None
        if parameters.get(self.EXTENT):
            rect = self.parameterAsExtent(parameters, self.EXTENT, context, metric_crs)
            if not rect.isEmpty():
                clip = QgsGeometry.fromRect(rect)

        feedback.pushInfo(self.tr("Lecture et réparation de la forêt…"))
        forest_u = self._dissolve(forest_src, metric_crs, clip, feedback, 0, 40)
        feedback.pushInfo(self.tr("Lecture et réparation du bâti…"))
        bati_u = self._dissolve(bati_src, metric_crs, clip, feedback, 40, 70)
        if feedback.isCanceled():
            return {}
        if forest_u.isEmpty() or bati_u.isEmpty():
            where = self.tr(" dans la zone d'étude") if clip is not None else ""
            raise QgsProcessingException(
                self.tr("La couche de forêt ou de bâti ne contient aucune géométrie{}.").format(
                    where
                )
            )

        feedback.pushInfo(self.tr("Calcul de la frontière et de la bande…"))
        # The real forest edge, before the study area cuts the forest (that cut is no frontier).
        edge = QgsGeometry(forest_u.constGet().boundary())
        if clip is not None:
            forest_u = forest_u.intersection(clip)
            bati_u = bati_u.intersection(clip)
            edge = edge.intersection(clip)
        reach = bati_u.buffer(contact_m, _BUFFER_SEGMENTS)
        zone = forest_u.intersection(reach)
        line = edge.intersection(reach)
        line.convertToMultiType()
        zone.convertToMultiType()
        feedback.setProgress(90)

        length_m = line.length()
        area_ha = zone.area() / 10_000.0
        feedback.pushInfo(
            f"Frontière : {length_m / 1000:.2f} km | bande de contact : {area_ha:.1f} ha"
        )
        if length_m == 0:
            feedback.reportError(
                self.tr(
                    "Aucune interface : la forêt et le bâti ne sont jamais à moins de la "
                    "distance de contact. Vérifiez les couches et la distance."
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

        from ._layers import style_output
        from ._styles import paff_line_qml, paff_zone_qml

        style_output(context, line_id, paff_line_qml())
        style_output(context, zone_id, paff_zone_qml())
        return {self.LINE_OUTPUT: line_id, self.ZONE_OUTPUT: zone_id}

    # --- helpers -------------------------------------------------------------
    def _dissolve(
        self,
        source: QgsProcessingFeatureSource,
        crs,
        clip: QgsGeometry | None,
        feedback: QgsProcessingFeedback,
        pct_from: int,
        pct_to: int,
    ) -> QgsGeometry:
        """Reproject, repair and dissolve the features of ``source`` (within ``clip``)."""
        to_crs = None
        request = QgsFeatureRequest()
        if source.sourceCrs() != crs:
            to_crs = QgsCoordinateTransform(source.sourceCrs(), crs, QgsProject.instance())
        if clip is not None:
            back = QgsCoordinateTransform(crs, source.sourceCrs(), QgsProject.instance())
            request.setFilterRect(back.transformBoundingBox(clip.boundingBox()))
        total = max(1, source.featureCount())
        geoms: list[QgsGeometry] = []
        features = source.getFeatures(request, _compat.SKIP_GEOMETRY_CHECKS)
        for i, feat in enumerate(features):
            if feedback.isCanceled():
                return QgsGeometry()
            geom = QgsGeometry(feat.geometry())
            if geom.isEmpty():
                continue
            if to_crs is not None:
                geom.transform(to_crs)
            if not geom.isGeosValid():
                geom = geom.makeValid()  # may add stray lines or points: keep the polygons
                geom.convertGeometryCollectionToSubclass(_compat.GEOMETRY_POLYGON)
            if clip is None or geom.intersects(clip):
                geoms.append(geom)
            if i % 500 == 0:
                feedback.setProgress(pct_from + (pct_to - pct_from) * min(1.0, i / total))
        if not geoms:
            return QgsGeometry()
        return QgsGeometry.unaryUnion(geoms)

    def _write_sink(
        self, parameters, name, context, crs, wkb_type, fields, geometry, attributes=None
    ) -> str:
        sink, dest_id = self.parameterAsSink(parameters, name, context, fields, wkb_type, crs)
        if sink is None:
            raise QgsProcessingException(self.tr(f"Impossible de créer la sortie « {name} »."))
        if not geometry.isEmpty():
            feat = QgsFeature(fields)
            feat.setGeometry(geometry)
            if attributes is not None:
                feat.setAttributes(attributes)
            sink.addFeature(feat, _compat.SINK_FAST_INSERT)
        return dest_id
