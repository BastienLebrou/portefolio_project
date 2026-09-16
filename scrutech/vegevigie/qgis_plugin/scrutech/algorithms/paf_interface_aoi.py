"""③ PAFF from an extent alone: forest↔built-up interface (Wildland-Urban Interface).

Draw an extent, set the contact distance (default 50 m = OLD débroussaillement), hit Run.
ScruTech fetches the forest (BD TOPO wooded zones) and buildings from the IGN Géoplateforme
for that emprise and computes the interface, with **no input layer required**. Needs the
external Python + internet (BD TOPO WFS).
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python


class InterfaceFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Wildland-Urban Interface derived from an extent only (BD TOPO forest + buildings)."""

    EXTENT = "EXTENT"
    CONTACT_M = "CONTACT_M"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "paf_interface_aoi"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("③ Interface habitat-forêt, risque incendie (PAFF)")

    def group(self) -> str:
        return self.tr("2 · Analyser une emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Trace la <b>ligne où la forêt touche les habitations</b> et la <b>bande à "
            "débroussailler</b> autour, là où le feu menace le plus les maisons. La forêt et le "
            "bâti sont téléchargés automatiquement (BD TOPO de l'IGN) : aucune couche à "
            "fournir.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude (une commune ou un quartier pour commencer).<br>"
            "2. Distance de contact : 50 m correspond à l'obligation légale de débroussaillement "
            "(OLD) ; adaptez-la si un arrêté préfectoral fixe une autre valeur.<br>"
            "3. Exécuter.</p>"
            "<p><b>Résultat</b><br>Deux couches : la frontière habitat-forêt (ligne) et la bande "
            "de débroussaillement (surface). Le journal donne la longueur en km et la surface "
            "en ha.</p>"
            "<p><b>Bon à savoir</b><br>Vous avez déjà vos propres couches forêt et bâti ? "
            "Utilisez « 5 · Outils avancés ▸ Interface habitat-forêt (couches en entrée) », qui "
            "fonctionne sans internet.</p>"
        )

    def createInstance(self) -> InterfaceFromAoiAlgorithm:  # noqa: N802
        return InterfaceFromAoiAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("paf")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
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
        contact_m = self.parameterAsDouble(parameters, self.CONTACT_M, context)
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "paf_interface_aoi",
            "bbox": list(bbox),
            "contact_m": contact_m,
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        length_km = float(payload.get("interface_length_m", 0.0)) / 1000.0
        band_ha = float(payload.get("interface_zone_ha", 0.0))
        feedback.pushInfo(
            f"Interface : {length_km:.2f} km de frontière | {band_ha:.1f} ha à débroussailler"
        )
        if length_km == 0:
            feedback.reportError(
                self.tr(
                    "Aucune interface trouvée : dans cette zone, la forêt et les bâtiments ne "
                    "sont jamais à moins de la distance de contact."
                )
            )

        self._queue_layers(payload, context)
        return {"LINE": payload.get("line_path"), "ZONE": payload.get("zone_path")}

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_paf"
        return Path(value)

    def _queue_layers(self, payload: dict, context: QgsProcessingContext) -> None:
        from ._layers import queue_layer
        from ._styles import paff_line_qml, paff_zone_qml

        pairs = [
            (payload.get("zone_path"), "PAFF : bande de débroussaillement", paff_zone_qml()),
            (payload.get("line_path"), "PAFF : frontière habitat-forêt", paff_line_qml()),
        ]
        for path, label, qml in pairs:
            if path:
                queue_layer(context, path, label, qml)
