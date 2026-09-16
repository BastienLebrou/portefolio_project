"""Écobuage algorithm: multi-criteria controlled-burn suitability scoring.

Feed aligned criterion rasters (all on the same grid) — combustible vegetation,
embroussaillement, slope, accessibility, fire history, plus an optional exclusion
mask — and get a weighted 0-100 aptitude raster and a 3-class zoning
(0 = à exclure, 1 = à étudier, 2 = prioritaire). Wraps the pure-numpy ``ecobuage``
scoring engine; reads/writes rasters with GDAL (bundled with QGIS), so it needs no
extra Python dependencies.

The criterion rasters must already be normalized as the engine expects: the 0-1
"favourable" layers (combustible, embroussaillement, access, history) in [0, 1],
and slope in percent (the exploitable band 15-40 %, ramp 10, is applied here).
"""

from __future__ import annotations

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat

# Slope's exploitable band (percent) and ramp — the README defaults.
_SLOPE_LO, _SLOPE_HI, _SLOPE_RAMP = 15.0, 40.0, 10.0


class EcobuageAptitudeAlgorithm(QgsProcessingAlgorithm):
    """Weighted multi-criteria écobuage aptitude map + 3-class zoning."""

    COMBUSTIBLE = "COMBUSTIBLE"
    EMBROUSSAILLEMENT = "EMBROUSSAILLEMENT"
    SLOPE = "SLOPE"
    ACCESS = "ACCESS"
    HIST = "HIST"
    EXCLUSION = "EXCLUSION"
    W_COMB = "W_COMB"
    W_EMBR = "W_EMBR"
    W_SLOPE = "W_SLOPE"
    W_ACCESS = "W_ACCESS"
    W_HIST = "W_HIST"
    APTITUDE = "APTITUDE"
    CLASSES = "CLASSES"

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
            "propres rasters de critères</b>, déjà préparés. Fonctionne sans internet et "
            "sans le Python de ScruTech.</p>"
            "<p><b>Avant de lancer</b><br>Tous les rasters doivent être <b>alignés</b> (même "
            "grille, même taille de pixel) : au besoin, utilisez l'outil de traitement "
            "« Aligner les rasters ». Valeurs attendues : combustible, embroussaillement, "
            "accessibilité et historique des feux entre 0 et 1 ; pente en %.</p>"
            "<p><b>Étapes</b><br>"
            "1. Choisissez les 5 rasters de critères et, si besoin, un raster d'exclusions "
            "(toute valeur supérieure à 0 est exclue).<br>"
            "2. Ajustez les poids si nécessaire (25/25/20/15/15 par défaut).<br>"
            "3. Exécuter.</p>"
            "<p><b>Résultat</b><br>L'aptitude (0 à 100) et les classes (0 à exclure, "
            "1 à étudier, 2 prioritaire). Le journal donne le nombre de pixels par "
            "classe.</p>"
        )

    def createInstance(self) -> EcobuageAptitudeAlgorithm:  # noqa: N802
        return EcobuageAptitudeAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("ecobuage")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        rasters = [
            (self.COMBUSTIBLE, "Combustible / biomasse sèche (0-1)"),
            (self.EMBROUSSAILLEMENT, "Embroussaillement (0-1)"),
            (self.SLOPE, "Pente (%)"),
            (self.ACCESS, "Accessibilité (0-1)"),
            (self.HIST, "Historique feux (0-1)"),
        ]
        for key, label in rasters:
            self.addParameter(QgsProcessingParameterRasterLayer(key, self.tr(label)))
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.EXCLUSION, self.tr("Exclusions (>0 = à exclure, optionnel)"), optional=True
            )
        )
        weights = [
            (self.W_COMB, "Poids combustible", 25.0),
            (self.W_EMBR, "Poids embroussaillement", 25.0),
            (self.W_SLOPE, "Poids pente", 20.0),
            (self.W_ACCESS, "Poids accessibilité", 15.0),
            (self.W_HIST, "Poids historique", 15.0),
        ]
        for key, label, default in weights:
            self.addParameter(
                QgsProcessingParameterNumber(
                    key,
                    self.tr(label),
                    type=_compat.NUMBER_DOUBLE,
                    defaultValue=default,
                    minValue=0.0,
                )
            )
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.APTITUDE, self.tr("Aptitude (0-100)"))
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.CLASSES, self.tr("Classes (0 exclure / 1 étudier / 2 prioritaire)")
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        import ecobuage
        from osgeo import gdal

        comb, gt, proj = self._read(parameters, self.COMBUSTIBLE, context)
        embr, _, _ = self._read(parameters, self.EMBROUSSAILLEMENT, context)
        slope, _, _ = self._read(parameters, self.SLOPE, context)
        access, _, _ = self._read(parameters, self.ACCESS, context)
        hist, _, _ = self._read(parameters, self.HIST, context)

        ref = comb.shape
        for name, arr in (
            ("embroussaillement", embr),
            ("pente", slope),
            ("accessibilité", access),
            ("historique", hist),
        ):
            if arr.shape != ref:
                raise QgsProcessingException(
                    self.tr(
                        f"Le raster « {name} » {arr.shape} n'est pas aligné sur le raster "
                        f"combustible {ref}. Alignez d'abord tous les rasters sur la même "
                        "grille (outil « Aligner les rasters »)."
                    )
                )

        exclusions = None
        excl_layer = self.parameterAsRasterLayer(parameters, self.EXCLUSION, context)
        if excl_layer is not None:
            excl, _, _ = self._read(parameters, self.EXCLUSION, context)
            if excl.shape == ref:
                exclusions = excl > 0
            else:
                feedback.reportError(self.tr("Raster d'exclusions non aligné : ignoré."))

        slope_score = ecobuage.band(slope, _SLOPE_LO, _SLOPE_HI, _SLOPE_RAMP)
        criteria = [
            (comb, self.parameterAsDouble(parameters, self.W_COMB, context)),
            (embr, self.parameterAsDouble(parameters, self.W_EMBR, context)),
            (slope_score, self.parameterAsDouble(parameters, self.W_SLOPE, context)),
            (access, self.parameterAsDouble(parameters, self.W_ACCESS, context)),
            (hist, self.parameterAsDouble(parameters, self.W_HIST, context)),
        ]
        try:
            score = ecobuage.aptitude(criteria, exclusions=exclusions)
        except ValueError as exc:
            raise QgsProcessingException(str(exc)) from exc
        classes = ecobuage.classify(score)

        apt_path = self.parameterAsOutputLayer(parameters, self.APTITUDE, context)
        cls_path = self.parameterAsOutputLayer(parameters, self.CLASSES, context)
        self._write(apt_path, score.astype("float32"), gt, proj, gdal.GDT_Float32)
        self._write(cls_path, classes.astype("uint8"), gt, proj, gdal.GDT_Byte)

        n_prio = int((classes == 2).sum())
        n_etud = int((classes == 1).sum())
        n_excl = int((classes == 0).sum())
        feedback.pushInfo(
            f"Pixels : prioritaire {n_prio} | à étudier {n_etud} | à exclure {n_excl}"
        )
        return {self.APTITUDE: apt_path, self.CLASSES: cls_path}

    # --- helpers -------------------------------------------------------------
    def _read(self, parameters, name, context):
        from osgeo import gdal

        layer = self.parameterAsRasterLayer(parameters, name, context)
        if layer is None:
            raise QgsProcessingException(self.tr(f"Raster « {name} » invalide."))
        ds = gdal.Open(layer.source())
        if ds is None:
            raise QgsProcessingException(
                self.tr(f"GDAL n'a pas pu ouvrir « {name} » ({layer.source()}).")
            )
        arr = ds.GetRasterBand(1).ReadAsArray().astype("float64")
        return arr, ds.GetGeoTransform(), ds.GetProjection()

    @staticmethod
    def _write(path, arr, gt, proj, gdal_dtype) -> None:
        from osgeo import gdal

        driver = gdal.GetDriverByName("GTiff")
        ys, xs = arr.shape
        ds = driver.Create(path, xs, ys, 1, gdal_dtype)
        ds.SetGeoTransform(gt)
        ds.SetProjection(proj)
        ds.GetRasterBand(1).WriteArray(arr)
        ds.FlushCache()
        ds = None
