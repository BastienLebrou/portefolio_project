"""Écobuage algorithm: multi-criteria controlled-burn suitability from your own rasters.

Give whatever criteria you have (a DEM for the slope, combustible, embroussaillement,
accessibility, fire history, exclusions): every raster is warped onto one metric grid (study
area × pixel size), so they need not be aligned beforehand, and missing criteria simply drop
out of the weighted mean. Outputs a 0-100 aptitude raster and a 3-class zoning (0 à exclure,
1 à étudier, 2 prioritaire), styled as in the AOI tool.

Wraps the pure-numpy ``ecobuage`` scoring engine; reads, warps and writes with GDAL (bundled
with QGIS), so it needs neither internet nor the ScruTech Python.
"""

from __future__ import annotations

import math

from qgis.core import (
    QgsCoordinateTransform,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterCrs,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat

# Slope's exploitable band (percent) and ramp: the engine defaults, as in the AOI tool.
_SLOPE_LO, _SLOPE_HI, _SLOPE_RAMP = 15.0, 40.0, 10.0
_NAN = float("nan")


# Même patron QGIS Processing que analyze_extent.py — mais ici tout le calcul reste
# DANS le processus QGIS (GDAL suffit, pas besoin d'interpréteur externe).
class EcobuageAptitudeAlgorithm(QgsProcessingAlgorithm):
    """Weighted multi-criteria écobuage aptitude map + 3-class zoning."""

    MNT = "MNT"
    COMBUSTIBLE = "COMBUSTIBLE"
    EMBROUSSAILLEMENT = "EMBROUSSAILLEMENT"
    ACCESS = "ACCESS"
    HIST = "HIST"
    EXCLUSION = "EXCLUSION"
    EXTENT = "EXTENT"
    RESOLUTION = "RESOLUTION"
    METRIC_CRS = "METRIC_CRS"
    W_COMB = "W_COMB"
    W_EMBR = "W_EMBR"
    W_SLOPE = "W_SLOPE"
    W_ACCESS = "W_ACCESS"
    W_HIST = "W_HIST"
    APTITUDE = "APTITUDE"
    CLASSES = "CLASSES"

    # (parameter, label, short name, weight parameter, default weight). The DEM is scored
    # through its slope.
    _CRITERIA = [
        (MNT, "MNT (la pente en est déduite)", "pente", W_SLOPE, 20.0),
        (COMBUSTIBLE, "Combustible, biomasse sèche (0 à 1)", "Combustible", W_COMB, 25.0),
        (EMBROUSSAILLEMENT, "Embroussaillement (0 à 1)", "Embroussaillement", W_EMBR, 25.0),
        (ACCESS, "Accessibilité (0 à 1)", "Accessibilité", W_ACCESS, 15.0),
        (HIST, "Historique des feux (0 à 1)", "Historique des feux", W_HIST, 15.0),
    ]

    def name(self) -> str:
        return "ecobuage_aptitude"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Aptitude à l'écobuage (couches en entrée)")

    def group(self) -> str:
        return self.tr("5 · Outils avancés (couches en entrée)")

    def groupId(self) -> str:  # noqa: N802
        return "avance"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Même notation que « ④ Aptitude à l'écobuage » mais à partir de <b>vos "
            "propres rasters</b>. Fonctionne sans internet et sans le Python de ScruTech.</p>"
            "<p><b>Étapes</b><br>"
            "1. Donnez les critères dont vous disposez, <b>tous facultatifs</b> (au moins un) : "
            "un MNT (la pente en est calculée), et des rasters de combustible, "
            "d'embroussaillement, d'accessibilité ou d'historique des feux notés de 0 "
            "(défavorable) à 1 (favorable). Un critère absent ne compte simplement pas.<br>"
            "2. Exclusions (facultatif) : tout pixel supérieur à 0 est classé « à exclure » "
            "(habitations, zones protégées…).<br>"
            "3. Zone d'étude (facultatif : vide = emprise du premier raster donné) et taille des "
            "pixels du résultat (25 m par défaut).<br>"
            "4. Exécuter.</p>"
            "<p><b>Résultat</b><br>L'aptitude (0 à 100) et les classes à exclure, à étudier, "
            "prioritaire, avec leur légende. Le journal donne la surface de chaque classe en "
            "ha.</p>"
            "<p><b>Bon à savoir</b><br>Les rasters n'ont pas besoin d'être alignés ni dans le "
            "même système de coordonnées : ScruTech les ramène sur une grille commune en "
            "Lambert-93. Un pixel sans donnée dans un critère reste sans donnée dans le "
            "résultat. Les poids (25/25/20/15/15) se règlent dans les paramètres avancés.</p>"
        )

    def createInstance(self) -> EcobuageAptitudeAlgorithm:  # noqa: N802
        return EcobuageAptitudeAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("ecobuage")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        for key, label, *_rest in self._CRITERIA:
            self.addParameter(QgsProcessingParameterRasterLayer(key, self.tr(label), optional=True))
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.EXCLUSION, self.tr("Exclusions (> 0 = à exclure)"), optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT,
                self.tr("Zone d'étude (facultatif : vide = emprise du premier raster)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Taille des pixels du résultat (m)"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=25.0,
                minValue=1.0,
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterCrs(
                    self.METRIC_CRS,
                    self.tr("Système de coordonnées métrique du résultat"),
                    defaultValue="EPSG:2154",
                )
            )
        )
        for _key, _label, short, weight, default in self._CRITERIA:
            self.addParameter(
                _compat.advanced(
                    QgsProcessingParameterNumber(
                        weight,
                        self.tr("Poids : {}").format(short.lower()),
                        type=_compat.NUMBER_DOUBLE,
                        defaultValue=default,
                        minValue=0.0,
                    )
                )
            )
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.APTITUDE, self.tr("Aptitude (0 à 100)"))
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.CLASSES, self.tr("Classes (à exclure, à étudier, prioritaire)")
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from osgeo import gdal

        with gdal.ExceptionMgr():  # GDAL errors raise here only, not in the rest of QGIS
            return self._run(parameters, context, feedback)

    def _run(self, parameters, context, feedback) -> dict:
        import ecobuage
        import numpy as np
        from osgeo import gdal

        layers = {
            key: self.parameterAsRasterLayer(parameters, key, context)
            for key, *_rest in self._CRITERIA
        }
        given = [key for key, *_rest in self._CRITERIA if layers[key] is not None]
        if not given:
            raise QgsProcessingException(
                self.tr("Donnez au moins un critère : un MNT ou un raster noté de 0 à 1.")
            )
        crs = self.parameterAsCrs(parameters, self.METRIC_CRS, context)
        if not crs.isValid() or crs.isGeographic():
            raise QgsProcessingException(
                self.tr("Le système de coordonnées du résultat doit être en mètres (EPSG:2154).")
            )
        res = self.parameterAsDouble(parameters, self.RESOLUTION, context)
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs)
        if not parameters.get(self.EXTENT) or rect.isEmpty():
            first = layers[given[0]]
            to_grid = QgsCoordinateTransform(first.crs(), crs, QgsProject.instance())
            rect = to_grid.transformBoundingBox(first.extent())
        width = max(1, math.ceil(rect.width() / res))
        height = max(1, math.ceil(rect.height() / res))
        if width * height > 25_000_000:
            raise QgsProcessingException(
                self.tr(
                    "Grille trop grande ({} × {} pixels) : réduisez la zone d'étude ou "
                    "augmentez la taille des pixels."
                ).format(width, height)
            )
        grid = _Grid(
            crs.toWkt(),
            (
                rect.xMinimum(),
                rect.yMaximum() - height * res,
                rect.xMinimum() + width * res,
                rect.yMaximum(),
            ),
            width,
            height,
            res,
        )
        feedback.pushInfo(f"Grille : {width} × {height} pixels de {res:g} m.")

        criteria = []
        for step, (key, label, short, weight_key, _default) in enumerate(self._CRITERIA):
            layer = layers[key]
            if layer is None:
                continue
            if feedback.isCanceled():
                return {}
            feedback.setProgress(10 + 70 * step / len(self._CRITERIA))
            source = self._gdal_source(layer, label)
            try:
                if key == self.MNT:
                    feedback.pushInfo(self.tr("Pente calculée depuis le MNT…"))
                    slope = self._slope(source, layer, grid)
                    if np.isnan(slope).all():
                        raise ValueError("« MNT » ne couvre pas la zone d'étude.")
                    value = ecobuage.band(slope, _SLOPE_LO, _SLOPE_HI, _SLOPE_RAMP)
                else:
                    value = grid.warp(source, "average")
                    ecobuage.check_unit(value, short)
            except (ValueError, RuntimeError) as exc:
                raise QgsProcessingException(str(exc)) from exc
            weight = self.parameterAsDouble(parameters, weight_key, context)
            criteria.append((value, weight))

        exclusions = None
        excl_layer = self.parameterAsRasterLayer(parameters, self.EXCLUSION, context)
        if excl_layer is not None:
            excl = grid.warp(self._gdal_source(excl_layer, "Exclusions"), "max")
            exclusions = excl > 0

        feedback.setProgress(85)
        try:
            score = ecobuage.aptitude(criteria, exclusions=exclusions)
        except ValueError as exc:
            raise QgsProcessingException(str(exc)) from exc
        classes = ecobuage.classify(score)

        apt_path = self.parameterAsOutputLayer(parameters, self.APTITUDE, context)
        cls_path = self.parameterAsOutputLayer(parameters, self.CLASSES, context)
        grid.write(apt_path, score.astype("float32"), gdal.GDT_Float32, _NAN)
        grid.write(cls_path, classes, gdal.GDT_Byte, ecobuage.NODATA_CLASS)

        pixel_ha = res * res / 10_000.0
        surfaces = " | ".join(
            f"{label} : {int((classes == value).sum()) * pixel_ha:.1f} ha"
            for value, label in ((2, "prioritaire"), (1, "à étudier"), (0, "à exclure"))
        )
        feedback.pushInfo(surfaces)

        from ._layers import style_output
        from ._styles import ecobuage_aptitude_qml, ecobuage_classes_qml

        style_output(context, apt_path, ecobuage_aptitude_qml())
        style_output(context, cls_path, ecobuage_classes_qml())
        return {self.APTITUDE: apt_path, self.CLASSES: cls_path}

    # --- helpers -------------------------------------------------------------
    def _gdal_source(self, layer, label: str) -> str:
        if layer.providerType() != "gdal":
            raise QgsProcessingException(
                self.tr("« {} » doit être un fichier raster (GeoTIFF…), pas un flux web.").format(
                    label
                )
            )
        return layer.source()

    @staticmethod
    def _slope(source: str, layer, grid: _Grid):
        """Slope (%) of the DEM on the grid: computed at up to 5 sub-pixels, then averaged."""
        from osgeo import gdal

        step = grid.res / 5
        if not layer.crs().isGeographic():  # native pixel in metres: never upsample it
            step = max(step, layer.rasterUnitsPerPixelX())
        margin = 2 * grid.res
        xmin, ymin, xmax, ymax = grid.bounds
        dem = "/vsimem/scrutech_mnt.tif"
        slope = "/vsimem/scrutech_pente.tif"
        try:
            gdal.Warp(
                dem,
                source,
                outputBounds=(xmin - margin, ymin - margin, xmax + margin, ymax + margin),
                xRes=step,
                yRes=step,
                dstSRS=grid.wkt,
                resampleAlg="bilinear",
                dstNodata=-9999.0,
                outputType=gdal.GDT_Float32,
            )
            gdal.DEMProcessing(slope, dem, "slope", slopeFormat="percent", computeEdges=True)
            return grid.warp(slope, "average")
        finally:
            gdal.Unlink(dem)
            gdal.Unlink(slope)


class _Grid:
    """The common output grid every criterion is warped onto."""

    def __init__(self, wkt: str, bounds: tuple, width: int, height: int, res: float) -> None:
        self.wkt, self.bounds, self.width, self.height, self.res = wkt, bounds, width, height, res

    def warp(self, source: str, resample: str):
        """``source`` band 1 on the grid as float64 (nodata and outside = NaN)."""
        from osgeo import gdal

        ds = gdal.Warp(
            "",
            source,
            format="MEM",
            outputBounds=self.bounds,
            width=self.width,
            height=self.height,
            dstSRS=self.wkt,
            resampleAlg=resample,
            dstNodata=_NAN,
            outputType=gdal.GDT_Float32,
        )
        return ds.GetRasterBand(1).ReadAsArray().astype("float64")

    def write(self, path: str, array, gdal_type: int, nodata: float) -> None:
        from osgeo import gdal

        ds = gdal.GetDriverByName("GTiff").Create(
            path, self.width, self.height, 1, gdal_type, options=["COMPRESS=DEFLATE"]
        )
        xmin, _ymin, _xmax, ymax = self.bounds
        ds.SetGeoTransform((xmin, self.res, 0.0, ymax, 0.0, -self.res))
        ds.SetProjection(self.wkt)
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(nodata)
        band.WriteArray(array)
        ds.FlushCache()
        ds = None
