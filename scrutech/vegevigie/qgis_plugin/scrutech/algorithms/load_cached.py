"""Load a previously computed ScruTech analysis for an AOI, with no recompute.

ScruTech caches every AOI run's outputs in the central store keyed by the area's id. This
algorithm resolves the extent to that id and loads the cached layers straight into the
project: instant, offline. Draw the same extent you analysed before and Run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
)
from qgis.PyQt.QtCore import QCoreApplication

from ._layers import queue_layer
from ._styles import style_for
from ._venv import python_param, require_python


class LoadCachedAlgorithm(QgsProcessingAlgorithm):
    """Load cached ScruTech products for an extent (no recomputation)."""

    EXTENT = "EXTENT"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "load_cached"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Recharger une analyse déjà calculée")

    def group(self) -> str:
        return self.tr("4 · Consulter les résultats")

    def groupId(self) -> str:  # noqa: N802
        return "restituer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Recharge dans le projet les couches <b>déjà calculées</b> pour une zone, sans "
            "refaire le calcul ni utiliser internet.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : <b>la même emprise</b> que lors de l'analyse.<br>"
            "2. Exécuter.</p>"
            "<p><b>Résultat</b><br>Toutes les couches trouvées pour cette zone (VegeVigie, "
            "AlphaEarth, PAFF, écobuage, Biotrame), avec leur style.</p>"
            "<p><b>Bon à savoir</b><br>Rien ne se charge ? L'emprise diffère sans doute de celle "
            "de l'analyse : reprenez exactement la même, par exemple depuis la même couche.</p>"
        )

    def createInstance(self) -> LoadCachedAlgorithm:  # noqa: N802
        return LoadCachedAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Zone d'étude (la même emprise que l'analyse)")
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))

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
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {"task": "load_cached", "bbox": list(bbox)}
        # The listing is quick; reuse the same spec-file plumbing in a temp folder.
        out_folder = Path(tempfile.gettempdir()) / "scrutech_load"
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        paths = payload.get("paths", [])
        if not paths:
            feedback.reportError(
                self.tr(
                    "Aucune analyse enregistrée pour cette zone (identifiant {}). Lancez d'abord "
                    "une analyse, ou reprenez exactement la même emprise."
                ).format(payload.get("aoi_id"))
            )
            return {"LOADED": 0}

        feedback.pushInfo(
            f"Chargement de {len(paths)} couche(s) pour la zone {payload.get('aoi_id')}."
        )
        self._queue_layers(paths, context)
        return {"LOADED": len(paths), "AOI": payload.get("aoi_id")}

    # --- helpers -------------------------------------------------------------
    def _queue_layers(self, paths: list, context: QgsProcessingContext) -> None:
        for path in paths:
            # store layout: {root}/{pilier}/aoi={id}/output/{file} → pilier at parents[2].
            pilier = Path(path).parents[2].name
            label = f"ScruTech (cache) : {pilier} · {Path(path).stem}"
            queue_layer(context, path, label, style_for(str(path)))
