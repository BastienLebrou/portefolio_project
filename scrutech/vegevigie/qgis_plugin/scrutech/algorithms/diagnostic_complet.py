"""« Diagnostic complet » : every emprise tool one after the other, then the report.

Runs ① VegeVigie, ② AlphaEarth, ③ PAFF, ④ écobuage and Biotrame on one extent as child
algorithms and hands each the outputs of the previous ones (vegetation trend and drought to
écobuage and Biotrame, the DEM downloaded for écobuage to Biotrame). A failing step is logged and
skipped, never fatal (a missing GEE key must not cost the rest), then the HTML report of the zone
is written and opened.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsProcessingOutputFile,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param


class DiagnosticCompletAlgorithm(QgsProcessingAlgorithm):
    """All the emprise analyses in a row, chained, then the report."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    REPORT = "REPORT"

    def name(self) -> str:
        return "diagnostic_complet"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Diagnostic complet (clé en main)")

    def group(self) -> str:
        return self.tr("2 · Analyser une emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Lance <b>toutes les analyses de la zone</b> l'une après l'autre, puis ouvre le "
            "<b>rapport de synthèse</b> : ① végétation (VegeVigie), ② changements "
            "(AlphaEarth), ③ interface habitat-forêt (PAFF), ④ aptitude à l'écobuage, puis la "
            "priorisation écologique (Biotrame).</p>"
            "<p>Chaque analyse profite des précédentes : la tendance et la sécheresse de la "
            "végétation nourrissent l'écobuage et Biotrame, et le MNT téléchargé pour "
            "l'écobuage sert aux zones humides de Biotrame.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet. Pour AlphaEarth, une clé Google "
            "Earth Engine : sans elle, cette étape est sautée et le reste continue.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : une commune ou un groupe de communes (1 000 km² au plus).<br>"
            "2. Période : 2020 à 2025 par défaut. AlphaEarth compare la première et la "
            "dernière année.<br>"
            "3. Dossier de résultats : un sous-dossier par analyse, et le rapport.<br>"
            "4. Exécuter : de quelques minutes à une demi-heure selon la taille de la zone.</p>"
            "<p><b>Résultat</b><br>Toutes les couches stylées, rangées dans le groupe "
            "« Diagnostic ScruTech », et le rapport ouvert dans le navigateur. Le journal "
            "récapitule les analyses réussies et celles sautées, avec la raison.</p>"
            "<p><b>Bon à savoir</b><br>Une analyse qui échoue n'arrête pas les autres. Chaque "
            "analyse reste disponible seule dans ce groupe pour affiner ses réglages.</p>"
        )

    def createInstance(self) -> DiagnosticCompletAlgorithm:  # noqa: N802
        return DiagnosticCompletAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
        )
        for key, label, default in (
            (self.START_YEAR, "Année de début", 2020),
            (self.END_YEAR, "Année de fin", 2025),
        ):
            self.addParameter(
                QgsProcessingParameterNumber(
                    key,
                    self.tr(label),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=default,
                    minValue=2016,
                    maxValue=2035,
                )
            )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterNumber(
                    self.RESOLUTION,
                    self.tr("Résolution de la végétation (m) : 60 conseillé"),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=60,
                    minValue=10,
                    maxValue=200,
                )
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Dossier de résultats")
            )
        )
        self.addOutput(QgsProcessingOutputFile(self.REPORT, self.tr("Rapport de synthèse")))

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from qgis import processing

        rect = self.parameterAsExtent(
            parameters, self.EXTENT, context, crs=QgsCoordinateReferenceSystem("EPSG:4326")
        )
        if rect.isEmpty():
            raise QgsProcessingException(
                self.tr("La zone d'étude est vide : choisissez une emprise.")
            )
        start = self.parameterAsInt(parameters, self.START_YEAR, context)
        end = self.parameterAsInt(parameters, self.END_YEAR, context)
        if start >= end:
            raise QgsProcessingException(
                self.tr("L'année de début doit précéder l'année de fin (au moins 2 années).")
            )
        root = self._resolve_output_folder(parameters, context)
        common = {
            # Same extent string for every step, so they all share one cache id and one report.
            "EXTENT": f"{rect.xMinimum()},{rect.xMaximum()},{rect.yMinimum()},"
            f"{rect.yMaximum()} [EPSG:4326]",
            "PYTHON_EXE": self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(),
        }
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)

        # (label, algorithm, sub-folder, extra parameters from the outputs of earlier steps)
        steps = [
            (
                "① Végétation (VegeVigie)",
                "scrutech:analyze_extent",
                "vegevigie",
                lambda out: {"START_YEAR": start, "END_YEAR": end, "RESOLUTION": resolution},
            ),
            (
                "② Changements (AlphaEarth)",
                "scrutech:alphaearth_change",
                "alphaearth",
                lambda out: {"YEAR1": start, "YEAR2": end},
            ),
            (
                "③ Interface habitat-forêt (PAFF)",
                "scrutech:paf_interface_aoi",
                "paff",
                lambda out: {},
            ),
            (
                "④ Aptitude à l'écobuage",
                "scrutech:ecobuage_aptitude_aoi",
                "ecobuage",
                lambda out: {"VEG_TREND": out.get("TREND"), "VEG_DROUGHT": out.get("DROUGHT")},
            ),
            (
                "Priorisation écologique (Biotrame)",
                "scrutech:biotrame_priority",
                "biotrame",
                lambda out: {"VEG_TREND": out.get("TREND"), "MNT": out.get("MNT")},
            ),
        ]
        multi = QgsProcessingMultiStepFeedback(len(steps) + 1, feedback)
        outputs: dict = {}
        done: list[str] = []
        skipped: list[tuple[str, str]] = []
        for i, (label, alg_id, folder, extra) in enumerate(steps):
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Annulé."))
            multi.setCurrentStep(i)
            feedback.pushInfo(f"=== {label}")
            params = {**common, **extra(outputs), "OUTPUT_FOLDER": str(root / folder)}
            params = {k: v for k, v in params.items() if v not in (None, "")}
            try:
                outputs.update(
                    processing.run(
                        alg_id, params, context=context, feedback=multi, is_child_algorithm=True
                    )
                )
                done.append(label)
            except Exception as exc:  # noqa: BLE001 — one failing step must not cost the rest
                if feedback.isCanceled():
                    raise QgsProcessingException(self.tr("Annulé.")) from exc
                skipped.append((label, str(exc).strip()))
                feedback.reportError(f"{label} : étape sautée. {exc}")

        if not done:
            raise QgsProcessingException(
                self.tr("Aucune analyse n'a abouti. ")
                + " | ".join(f"{label} : {why}" for label, why in skipped)
            )
        multi.setCurrentStep(len(steps))
        feedback.pushInfo("=== Rapport de synthèse")
        report = str(root / "rapport_diagnostic.html")
        try:
            processing.run(
                "scrutech:report_launch",
                {**common, "OUTPUT": report},
                context=context,
                feedback=multi,
                is_child_algorithm=True,
            )
        except Exception as exc:  # noqa: BLE001 — the layers are there even without the page
            feedback.reportError(f"Rapport non généré : {exc}")
            report = ""

        for layer_id in context.layersToLoadOnCompletion():
            details = context.layerToLoadOnCompletionDetails(layer_id)
            details.groupName = self.tr("Diagnostic ScruTech")
        feedback.pushInfo(
            f"Diagnostic terminé : {len(done)} analyse(s) sur {len(steps)} réussie(s)."
        )
        for label, why in skipped:
            feedback.pushWarning(f"{label} sautée : {why}")
        return {self.OUTPUT_FOLDER: str(root), self.REPORT: report}

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_diagnostic"
        return Path(value)
