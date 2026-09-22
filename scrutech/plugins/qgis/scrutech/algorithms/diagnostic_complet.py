"""« Diagnostic complet » : every emprise tool one after the other, then the report.

Downloads the IGN DEM first, then runs ① VegeVigie, ② AlphaEarth, ③ PAFF, ④ écobuage and
Biotrame on one extent as child algorithms, handing each the outputs of the previous ones (the
DEM to écobuage and Biotrame, vegetation trend and drought to écobuage, the trend to Biotrame). A
failing step is logged and skipped, never fatal (a missing GEE key must not cost the rest), then
the HTML report of the zone is written and opened. Shown above the numbered groups: it is the
entry point for a first diagnostic, the groups are for tuning one analysis.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsProcessingOutputFile,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
    QgsProject,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param

# Biotrame hexagon sizes offered to the user: (label, H3 resolution).
_HEXAGONS = [
    ("Grands (≈ 5 km², pour un territoire)", 7),
    ("Moyens (≈ 70 ha, conseillé pour une commune)", 8),
    ("Fins (≈ 10 ha)", 9),
    ("Très fins (≈ 1,5 ha, pour une petite zone)", 10),
]
_MNT_BEST_M = 5.0  # the DEM is fetched at 5 m when the zone allows it (sharper slopes)
_MNT_MAX_PX = 25_000_000  # same limit as core.sources.MNT_MAX_PX (the engine refuses above)


class DiagnosticCompletAlgorithm(QgsProcessingAlgorithm):
    """The DEM, then all the emprise analyses in a row, chained, then the report."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    PIXEL = "PIXEL"
    HEXAGONS = "HEXAGONS"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    REPORT = "REPORT"

    def name(self) -> str:
        return "diagnostic_complet"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Diagnostic complet (clé en main)")

    def group(self) -> str:
        return ""  # no group: listed above the numbered groups, at the top of ScruTech

    def groupId(self) -> str:  # noqa: N802
        return ""

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Le <b>diagnostic de territoire en une fois</b> : ScruTech télécharge le MNT de "
            "la zone, lance toutes les analyses l'une après l'autre, puis ouvre le <b>rapport "
            "de synthèse</b>.</p>"
            "<p>Dans l'ordre : MNT IGN, ① végétation (VegeVigie), ② changements (AlphaEarth), "
            "③ interface habitat-forêt (PAFF), ④ aptitude à l'écobuage, priorisation "
            "écologique (Biotrame), projection climatique à 10, 15, 20 et 30 ans. Chaque "
            "analyse profite des précédentes : le MNT sert à "
            "l'écobuage et aux zones humides de Biotrame, la tendance et la sécheresse de la "
            "végétation nourrissent l'écobuage et Biotrame.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet. Pour AlphaEarth, une clé Google "
            "Earth Engine : sans elle, cette étape est sautée et le reste continue.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : une commune ou un groupe de communes.<br>"
            "2. Années d'analyse : 2020 à 2025 par défaut (au moins 2 années). AlphaEarth "
            "compare la première et la dernière.<br>"
            "3. Précision : la taille du pixel de la végétation et de l'écobuage. 30 m par "
            "défaut ; 10 m pour une petite zone, 60 m pour une grande.<br>"
            "4. Précision de Biotrame : la taille des hexagones.<br>"
            "5. Dossier de résultats : un sous-dossier par analyse, et le rapport.<br>"
            "6. Exécuter : de quelques minutes à une demi-heure selon la zone.</p>"
            "<p><b>Résultat</b><br>Toutes les couches stylées, rangées dans le groupe "
            "« Diagnostic ScruTech », et le rapport ouvert dans le navigateur. Le journal "
            "récapitule les analyses réussies et celles sautées, avec la raison.</p>"
            "<p><b>Bon à savoir</b><br>Plus le pixel est fin, plus la zone doit être petite : à "
            "30 m sur 6 ans, la végétation accepte environ 250 km² ; à 60 m, environ 1 000 km². "
            "Une analyse refusée ou en échec n'arrête pas les autres. Pour affiner une "
            "analyse, relancez-la seule depuis son groupe.</p>"
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
            QgsProcessingParameterNumber(
                self.PIXEL,
                self.tr("Précision : taille du pixel (m), 30 conseillé"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=30,
                minValue=10,
                maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.HEXAGONS,
                self.tr("Précision de Biotrame : taille des hexagones"),
                options=[self.tr(label) for label, _res in _HEXAGONS],
                defaultValue=1,
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

        from ._layers import queue_layer

        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
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
        pixel = self.parameterAsInt(parameters, self.PIXEL, context)
        hexagons = _HEXAGONS[self.parameterAsEnum(parameters, self.HEXAGONS, context)][1]
        root = self._resolve_output_folder(parameters, context)
        common = {
            # Same extent string for every step, so they all share one cache id and one report.
            "EXTENT": f"{rect.xMinimum()},{rect.xMaximum()},{rect.yMinimum()},"
            f"{rect.yMaximum()} [EPSG:4326]",
            "PYTHON_EXE": self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(),
        }
        mnt_path = str(root / "mnt" / "mnt.tif")

        # (label, algorithm, parameters given the outputs of the steps before it)
        steps = [
            (
                "MNT IGN de la zone",
                "scrutech:mnt_aoi",
                lambda out: {"RESOLUTION": self._mnt_resolution(rect, pixel), "OUTPUT": mnt_path},
            ),
            (
                "① Végétation (VegeVigie)",
                "scrutech:analyze_extent",
                lambda out: {
                    "START_YEAR": start,
                    "END_YEAR": end,
                    "RESOLUTION": pixel,
                    "OUTPUT_FOLDER": str(root / "vegevigie"),
                },
            ),
            (
                "② Changements (AlphaEarth)",
                "scrutech:alphaearth_change",
                lambda out: {
                    "YEAR1": start,
                    "YEAR2": end,
                    "OUTPUT_FOLDER": str(root / "alphaearth"),
                },
            ),
            (
                "③ Interface habitat-forêt (PAFF)",
                "scrutech:paf_interface_aoi",
                lambda out: {"OUTPUT_FOLDER": str(root / "paff")},
            ),
            (
                "④ Aptitude à l'écobuage",
                "scrutech:ecobuage_aptitude_aoi",
                lambda out: {
                    "MNT": out.get("OUTPUT"),
                    "RESOLUTION": pixel,
                    "VEG_TREND": out.get("TREND"),
                    "VEG_DROUGHT": out.get("DROUGHT"),
                    "OUTPUT_FOLDER": str(root / "ecobuage"),
                },
            ),
            (
                "Priorisation écologique (Biotrame)",
                "scrutech:biotrame_priority",
                lambda out: {
                    "RESOLUTION": hexagons,
                    "VEG_TREND": out.get("TREND"),
                    "MNT": out.get("OUTPUT") or out.get("MNT"),
                    "OUTPUT_FOLDER": str(root / "biotrame"),
                },
            ),
            (
                "Projection climatique 2035-2055",
                "scrutech:projection_climat",
                lambda out: {"OUTPUT_FOLDER": str(root / "projection")},
            ),
        ]
        multi = QgsProcessingMultiStepFeedback(len(steps) + 1, feedback)
        outputs: dict = {}
        done: list[str] = []
        skipped: list[tuple[str, str]] = []
        for i, (label, alg_id, step_params) in enumerate(steps):
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Annulé."))
            multi.setCurrentStep(i)
            feedback.pushInfo(f"=== {label}")
            params = {**common, **step_params(outputs)}
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
        if outputs.get("OUTPUT"):
            queue_layer(context, outputs["OUTPUT"], self.tr("MNT IGN de la zone"))

        if not set(done) - {steps[0][0]}:  # no analysis at all, at most the DEM
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
        feedback.pushInfo(f"Diagnostic terminé : {len(done)} étape(s) sur {len(steps)} réussie(s).")
        for label, why in skipped:
            feedback.pushWarning(f"{label} sautée : {why}")
        return {self.OUTPUT_FOLDER: str(root), self.REPORT: report}

    @staticmethod
    def _mnt_resolution(rect, pixel: int) -> float:
        """5 m when the zone fits the IGN DEM download limit at 5 m, else the analysis pixel."""
        to_l93 = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsCoordinateReferenceSystem("EPSG:2154"),
            QgsProject.instance(),
        )
        box = to_l93.transformBoundingBox(rect)
        fits = (box.width() / _MNT_BEST_M) * (box.height() / _MNT_BEST_M) <= _MNT_MAX_PX
        return _MNT_BEST_M if fits else float(pixel)

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_diagnostic"
        return Path(value)
