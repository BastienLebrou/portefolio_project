"""② AlphaEarth change detection over an extent (AOI + two years).

Draw an extent, pick two years, hit Run. ScruTech queries Google Earth Engine for the
AlphaEarth annual embeddings and returns the pixels whose 64-D signature changed most
between the two years (server-side cosine distance: a real surface change, not an
atmospheric artefact). **No input data**: only a study area and two years.

Needs the external Python (has ``earthengine-api``) and a GEE service-account key: a .json
file, the ``SCRUTECH_GEE_CREDENTIALS`` environment variable, or a QGIS authentication entry
(config key ``json_credentials``). The key is passed to the engine through an environment
variable, never written to disk.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsAuthMethodConfig,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python


class AlphaEarthChangeAlgorithm(QgsProcessingAlgorithm):
    """Year-over-year AlphaEarth change over an extent (GEE cosine distance)."""

    EXTENT = "EXTENT"
    YEAR1 = "YEAR1"
    YEAR2 = "YEAR2"
    PERCENTILE = "PERCENTILE"
    MAX_PIXELS = "MAX_PIXELS"
    KEY_FILE = "KEY_FILE"
    AUTH_ID = "AUTH_ID"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "alphaearth_change"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("② Changements entre deux années (AlphaEarth)")

    def group(self) -> str:
        return self.tr("2 · Analyser une emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Repère les endroits où <b>le terrain a changé</b> entre deux années "
            "(construction, coupe, culture, incendie…), à partir des « empreintes » satellite "
            "AlphaEarth de Google. Aucune couche à fournir : une zone et deux années "
            "suffisent.</p>"
            "<p><b>Avant de lancer</b><br>"
            "1. Avoir lancé « 0 · Démarrer ici ▸ Vérifier et installer ScruTech ».<br>"
            "2. Une <b>clé Google Earth Engine</b> (fichier .json d'un compte de service). "
            "Rangez-la dans <b>C:\\Users\\&lt;vous&gt;\\.scrutech\\gee_key.json</b> : elle "
            "est alors trouvée toute seule. « Vérifier et installer ScruTech » explique "
            "comment l'obtenir et teste l'accès.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude (commencez petit).<br>"
            "2. Deux années différentes (données disponibles depuis 2017).<br>"
            "3. Clé Google Earth Engine : laissez vide si elle est rangée à l'emplacement "
            "ci-dessus, sinon choisissez le fichier .json.<br>"
            "4. Exécuter.</p>"
            "<p><b>Résultat</b><br>Deux couches : tous les pixels analysés avec leur score de "
            "changement, et les candidats au-dessus du seuil (par défaut les 5 % qui ont le "
            "plus changé).</p>"
            "<p><b>Bon à savoir</b><br>Le calcul se fait chez Google et consomme votre quota "
            "Earth Engine ; le nombre de pixels analysés est plafonné pour le protéger. "
            "ScruTech n'écrit jamais la clé sur le disque.</p>"
        )

    def createInstance(self) -> AlphaEarthChangeAlgorithm:  # noqa: N802
        return AlphaEarthChangeAlgorithm()

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
                self.YEAR1,
                self.tr("Première année"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2018,
                minValue=2017,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.YEAR2,
                self.tr("Seconde année"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2023,
                minValue=2017,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.KEY_FILE,
                self.tr("Clé Google Earth Engine (.json ; vide = ~/.scrutech/gee_key.json)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
                extension="json",
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PERCENTILE,
                self.tr("Seuil de changement (percentile : 95 = les 5 % qui changent le plus)"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=95.0,
                minValue=50.0,
                maxValue=99.9,
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterNumber(
                    self.MAX_PIXELS,
                    self.tr("Points analysés (5 000 au maximum, limite d'Earth Engine)"),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=5000,
                    minValue=500,
                    maxValue=5000,
                )
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterString(
                    self.AUTH_ID,
                    self.tr("Identifiant d'authentification QGIS contenant la clé (facultatif)"),
                    defaultValue="gee_service",
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
        year1 = self.parameterAsInt(parameters, self.YEAR1, context)
        year2 = self.parameterAsInt(parameters, self.YEAR2, context)
        if year1 == year2:
            raise QgsProcessingException(self.tr("Choisissez deux années différentes."))
        percentile = self.parameterAsDouble(parameters, self.PERCENTILE, context)
        max_pixels = self.parameterAsInt(parameters, self.MAX_PIXELS, context)
        auth_id = self.parameterAsString(parameters, self.AUTH_ID, context).strip()
        key_file = self.parameterAsString(parameters, self.KEY_FILE, context).strip()
        out_folder = self._resolve_output_folder(parameters, context)

        credentials = self._read_credentials(key_file, auth_id)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "alphaearth_change",
            "bbox": list(bbox),
            "year1": year1,
            "year2": year2,
            "percentile": percentile,
            "max_pixels": max_pixels,
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(
                python_exe,
                "vegevigie.qgis_runner",
                spec,
                out_folder,
                feedback,
                extra_env={"SCRUTECH_GEE_CREDENTIALS": credentials},
            )
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"Changements {year1}→{year2} : {payload.get('n_changed', 0)} pixels sur "
            f"{payload.get('n_pixels', 0)} au-dessus du percentile {percentile:.0f} "
            f"(seuil {payload.get('threshold')})."
        )
        self._queue_layers(payload, context, year1, year2)
        return {"CHANGED": payload.get("changed_path"), "ALL": payload.get("geojson_path")}

    # --- helpers -------------------------------------------------------------
    def _read_credentials(self, key_file: str, auth_id: str) -> str:
        """Service-account JSON (compacted to one line), tried: key file → env → QgsAuthManager."""
        import json
        import os

        from ._setup import DEFAULT_GEE_KEY, check_gee_key

        raw = None
        if key_file:
            path = Path(key_file)
            if not path.exists():
                raise QgsProcessingException(
                    self.tr("Fichier de clé introuvable : {}").format(key_file)
                )
            raw = path.read_text(encoding="utf-8")
        elif os.environ.get("SCRUTECH_GEE_CREDENTIALS"):
            raw = os.environ["SCRUTECH_GEE_CREDENTIALS"]
        elif DEFAULT_GEE_KEY.is_file():
            raw = DEFAULT_GEE_KEY.read_text(encoding="utf-8")
        else:
            config = self._auth_config(auth_id) if auth_id else None
            raw = config.configMap().get("json_credentials") if config else None
        if not raw:
            raise QgsProcessingException(
                self.tr(
                    "Aucune clé Google Earth Engine. Rangez le fichier .json de votre compte de "
                    "service dans {} (ou choisissez-le dans « Clé Google Earth Engine »). Pour "
                    "l'obtenir, lancez « 0 · Démarrer ici ▸ Vérifier et installer ScruTech »."
                ).format(DEFAULT_GEE_KEY)
            )
        problems = check_gee_key(raw)
        if problems:
            raise QgsProcessingException(
                self.tr("Clé Google Earth Engine invalide : {}.").format(" ; ".join(problems))
            )
        return json.dumps(json.loads(raw))  # one line, so it crosses the subprocess env safely

    def _auth_config(self, auth_id: str) -> QgsAuthMethodConfig | None:
        """Load a complete auth config on QGIS 4, with QGIS 3 compatibility."""
        manager = QgsApplication.authManager()
        legacy_loader = getattr(manager, "authMethodConfig", None)
        if legacy_loader is not None:
            return legacy_loader(auth_id)

        config = QgsAuthMethodConfig()
        return config if manager.loadAuthenticationConfig(auth_id, config, True) else None

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_alphaearth"
        return Path(value)

    def _queue_layers(self, payload: dict, context, year1: int, year2: int) -> None:
        pairs = [
            (payload.get("geojson_path"), f"AlphaEarth : changements {year1}→{year2} (tous)"),
            (payload.get("changed_path"), f"AlphaEarth : changements {year1}→{year2} (candidats)"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
