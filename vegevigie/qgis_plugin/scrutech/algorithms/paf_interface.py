"""PAF algorithm: forest/built-up interface (Wildland-Urban Interface).

Pick a forest layer and a built-up layer, set the contact distance (default 50 m,
the French OLD débroussaillement footprint), hit Run — ScruTech computes the
frontier line where forest meets buildings and the contact band to defend, and
loads both into the project. Wraps the shared :mod:`vegevigie.interface` engine.

Geometry maths run in a projected CRS (metres); pick the *Metric CRS* to match the
territory (Lambert-93 for metropolitan France). Inputs in any CRS are reprojected
by the engine.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorDestination,
    QgsProcessingUtils,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import QCoreApplication


class InterfaceHabitatForetAlgorithm(QgsProcessingAlgorithm):
    """Forest/built-up interface (WUI): frontier line + contact band."""

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
            "reported in the log."
        )

    def createInstance(self) -> InterfaceHabitatForetAlgorithm:  # noqa: N802
        return InterfaceHabitatForetAlgorithm()

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFeatureSource(self.FOREST, self.tr("Forest zones"))
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(self.BATI, self.tr("Built-up zones"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CONTACT_M,
                self.tr("Contact distance (m) — OLD débroussaillement = 50"),
                type=QgsProcessingParameterNumber.Double,
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
            QgsProcessingParameterVectorDestination(
                self.LINE_OUTPUT, self.tr("Interface line (frontier)")
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorDestination(
                self.ZONE_OUTPUT, self.tr("Interface zone (contact band)")
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from ..dependencies import install_hint, missing_dependencies

        missing = missing_dependencies()
        if missing:
            raise QgsProcessingException(install_hint(missing))

        import geopandas as gpd

        from vegevigie.interface import forest_bati_interface

        contact_m = self.parameterAsDouble(parameters, self.CONTACT_M, context)
        metric_crs = self.parameterAsCrs(parameters, self.METRIC_CRS, context)
        if not metric_crs.isValid() or metric_crs.isGeographic():
            raise QgsProcessingException(
                self.tr(
                    "Metric CRS must be a projected (metre-based) CRS, e.g. EPSG:2154 — "
                    "distances in degrees are meaningless."
                )
            )
        crs_authid = metric_crs.authid() or "EPSG:2154"

        tmp = Path(QgsProcessingUtils.tempFolder()) / "scrutech_paf"
        tmp.mkdir(parents=True, exist_ok=True)
        forest_path = self._source_to_gpkg(parameters, self.FOREST, context, tmp / "forest.gpkg")
        bati_path = self._source_to_gpkg(parameters, self.BATI, context, tmp / "bati.gpkg")

        feedback.pushInfo(f"Computing interface (contact {contact_m:.0f} m, {crs_authid})…")
        try:
            result = forest_bati_interface(
                gpd.read_file(forest_path),
                gpd.read_file(bati_path),
                metric_crs=crs_authid,
                contact_m=contact_m,
            )
        except Exception as exc:  # noqa: BLE001
            raise QgsProcessingException(f"Interface computation failed: {exc}") from exc

        m = result.metrics
        feedback.pushInfo(
            f"Frontier: {m['interface_length_m'] / 1000:.2f} km | "
            f"contact band: {m['interface_zone_ha']:.1f} ha"
        )
        if m["interface_length_m"] == 0:
            feedback.reportError(
                self.tr("No interface found: forest and built-up never come within the "
                        "contact distance. Check the layers and the distance.")
            )

        line_out = self.parameterAsOutputLayer(parameters, self.LINE_OUTPUT, context)
        zone_out = self.parameterAsOutputLayer(parameters, self.ZONE_OUTPUT, context)
        self._write(result.line, line_out)
        self._write(result.zone, zone_out)
        feedback.pushInfo(f"Wrote {line_out} and {zone_out}")
        return {self.LINE_OUTPUT: line_out, self.ZONE_OUTPUT: zone_out}

    # --- helpers -------------------------------------------------------------
    def _source_to_gpkg(self, parameters, name, context, dest: Path) -> str:
        """Export an input feature source to a GeoPackage the engine can read."""
        layer = self.parameterAsVectorLayer(parameters, name, context)
        if layer is None:
            raise QgsProcessingException(self.tr(f"Input '{name}' is not a valid vector layer."))
        QgsVectorFileWriter.writeAsVectorFormat(layer, str(dest), "utf-8", layer.crs(), "GPKG")
        return str(dest)

    @staticmethod
    def _write(gdf, out_path: str) -> None:
        """Write a (possibly empty) GeoDataFrame to the Processing output path as GPKG."""
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        if len(gdf) and not gdf.geometry.is_empty.all():
            gdf.to_file(out_path, driver="GPKG")
        else:
            # Keep a valid (empty) layer so the run still produces the declared output.
            gdf.iloc[0:0].to_file(out_path, driver="GPKG")
