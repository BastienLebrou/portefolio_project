"""Biotrame: hexagonal ecological-priority mesh from an extent alone.

Draw an extent, hit Run. ScruTech builds an H3 hexagon mesh over the emprise, fetches the
biodiversity reservoirs (Natura 2000 / ZNIEFF) for it, and scores each hexagon's need for
ecological action by crossing enjeu × connectivité (× dégradation if a VegeVigie trend
raster is supplied). **No input layers**: just a study area. Needs the external Python +
internet (Géoplateforme WFS).
"""

from __future__ import annotations

import os
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._layers import queue_layer
from ._venv import python_param, require_python


# Même patron QGIS Processing que analyze_extent.py.
class BiotramePriorityAlgorithm(QgsProcessingAlgorithm):
    """Hexagonal ecological-priority mesh (enjeu × connectivité × dégradation)."""

    EXTENT = "EXTENT"
    RESOLUTION = "RESOLUTION"
    VEG_TREND = "VEG_TREND"
    MNT = "MNT"
    TVB_WFS = "TVB_WFS"
    TVB_TYPENAME = "TVB_TYPENAME"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "biotrame_priority"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Priorisation écologique (Biotrame)")

    def group(self) -> str:
        return self.tr("3 · Croiser et prioriser")

    def groupId(self) -> str:  # noqa: N802
        return "prioriser"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Découpe la zone en <b>hexagones</b> et note chacun de 0 à 100 selon le "
            "<b>besoin d'agir pour la nature</b> : présence de réservoirs de biodiversité "
            "(Natura 2000, ZNIEFF), connectivité entre eux et, si vous la fournissez, "
            "dégradation de la végétation. Utile pour cibler une restauration ou une "
            "compensation écologique.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet : les réservoirs sont téléchargés "
            "automatiquement.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude.<br>"
            "2. Taille des hexagones : 8 (environ 0,7 km²) convient à une commune, 7 à un "
            "territoire plus large.<br>"
            "3. Facultatif : la tendance produite par ① VegeVigie (axe dégradation) et un MNT "
            ".tif (repère les zones humides probables).<br>"
            "4. Exécuter.</p>"
            "<p><b>Résultat</b><br>Une couche d'hexagones stylée : score de 0 à 100 et classe "
            "de priorité.</p>"
            "<p><b>Bon à savoir</b><br>Sans corridors régionaux, la connectivité est estimée "
            "par la proximité aux réservoirs. Pour utiliser les vrais corridors de la Trame "
            "verte et bleue de votre région, renseignez son service WFS dans les paramètres "
            "avancés.</p>"
        )

    def createInstance(self) -> BiotramePriorityAlgorithm:  # noqa: N802
        return BiotramePriorityAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Taille des hexagones (7 ≈ 5 km², 8 ≈ 0,7 km², 9 ≈ 0,1 km²)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=8,
                minValue=5,
                maxValue=10,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_TREND,
                self.tr("Tendance VegeVigie (facultatif, axe dégradation)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.MNT,
                self.tr("MNT .tif (facultatif, pour les zones humides)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterString(
                    self.TVB_WFS,
                    self.tr("Adresse du WFS des corridors TVB régionaux (facultatif)"),
                    optional=True,
                )
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterString(
                    self.TVB_TYPENAME,
                    self.tr("Nom de la couche des corridors dans ce WFS (facultatif)"),
                    optional=True,
                )
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Dossier de résultats")
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(
                self.tr("La zone d'étude est vide : choisissez une emprise.")
            )
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        tvb_wfs = self.parameterAsString(
            parameters, self.TVB_WFS, context
        ).strip() or os.environ.get("SCRUTECH_TVB_WFS", "")
        tvb_typename = self.parameterAsString(
            parameters, self.TVB_TYPENAME, context
        ).strip() or os.environ.get("SCRUTECH_TVB_TYPENAME", "")
        mnt = self.parameterAsString(parameters, self.MNT, context).strip() or os.environ.get(
            "SCRUTECH_MNT", ""
        )
        spec = {
            "task": "biotrame_aoi",
            "bbox": list(bbox),
            "resolution": resolution,
            "out_folder": str(out_folder),
            "veg_trend_tif": self._raster_source(parameters, self.VEG_TREND, context),
            "mnt_path": mnt or None,
            "tvb_wfs_url": tvb_wfs or None,
            "tvb_typename": tvb_typename or None,
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"Biotrame : {payload.get('n_prioritaire', 0)} hexagones prioritaires sur "
            f"{payload.get('n_hexagons', 0)} | réservoirs : {payload.get('n_reservoirs', 0)} | "
            f"connectivité : {payload.get('connectivity_source')} | axes : {payload.get('axes')}"
        )
        if payload.get("geojson_path"):
            from ._styles import biotrame_qml

            queue_layer(
                context,
                payload["geojson_path"],
                "Biotrame : priorisation écologique",
                biotrame_qml(),
            )
        return {"MESH": payload.get("geojson_path"), "PARQUET": payload.get("parquet_path")}

    # --- helpers -------------------------------------------------------------
    def _raster_source(self, parameters, name, context) -> str | None:
        layer = self.parameterAsRasterLayer(parameters, name, context)
        return layer.source() if layer is not None else None

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_biotrame"
        return Path(value)
