"""« Vérifier et installer ScruTech »: the first tool a new user runs.

Reports, in plain French, whether the other tools can run (external Python, internet,
optional Google Earth Engine key and DEM) and, only when the user ticks the box, builds the
external Python with uv. Safe to run any number of times.
"""

from __future__ import annotations

import os
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsBlockingNetworkRequest,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from . import _qgis_compat as _compat
from . import _setup, _venv

_SERVICES = (
    (
        "images Sentinel-2 (Planetary Computer)",
        "https://planetarycomputer.microsoft.com/api/stac/v1",
    ),
    ("données IGN : forêt, bâti, routes (Géoplateforme)", "https://data.geopf.fr/"),
    ("limites des communes (geo.api.gouv.fr)", "https://geo.api.gouv.fr/departements"),
)

_GEE_STEPS = (
    "Pour obtenir une clé :\n"
    "  1. Créez un projet Google Cloud et enregistrez-le pour Earth Engine\n"
    "     (https://code.earthengine.google.com/register, gratuit en usage non commercial).\n"
    "  2. Dans ce projet, créez un compte de service et donnez-lui les rôles\n"
    "     « Earth Engine Resource Viewer » et « Service Usage Consumer ».\n"
    "  3. Créez une clé JSON pour ce compte, rangez le fichier en lieu sûr (jamais dans un\n"
    "     dossier partagé) et indiquez-le dans l'outil AlphaEarth."
)


class SetupCheckAlgorithm(QgsProcessingAlgorithm):
    """Check that ScruTech can run, and install its external Python on request."""

    INSTALL = "INSTALL"
    GEE_KEY = "GEE_KEY"
    UV_EXE = "UV_EXE"

    def name(self) -> str:
        return "setup_check"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Vérifier et installer ScruTech")

    def group(self) -> str:
        return self.tr("0 · Démarrer ici")

    def groupId(self) -> str:  # noqa: N802
        return "demarrer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>À lancer <b>en premier</b>, puis chaque fois qu'un outil signale un problème. "
            "Il vérifie que tout est prêt et dit quoi faire sinon.</p>"
            "<p><b>Première utilisation</b><br>"
            "1. Cochez « Installer ou mettre à jour le Python de ScruTech ».<br>"
            "2. Cliquez sur Exécuter. L'installation télécharge environ 1 Go, dure quelques "
            "minutes et ne se fait qu'une fois. Elle ne modifie pas votre QGIS : les calculs "
            "lourds tournent dans un Python à part.<br>"
            "3. Si le programme gratuit « uv » manque, le journal explique comment "
            "l'installer en une ligne.</p>"
            "<p><b>Ce qui est vérifié</b><br>"
            "1. Le Python de ScruTech et ses modules.<br>"
            "2. L'accès internet aux services utilisés (images satellite, données IGN, "
            "communes).<br>"
            "3. La clé Google Earth Engine, si vous en indiquez une (seulement pour "
            "AlphaEarth).<br>"
            "4. Le MNT déclaré, s'il y en a un (écobuage, zones humides de Biotrame).</p>"
            "<p><b>Résultat</b><br>Le journal liste chaque point : [OK], [À FAIRE] ou "
            "[FACULTATIF].</p>"
        )

    def createInstance(self) -> SetupCheckAlgorithm:  # noqa: N802
        return SetupCheckAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("data")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INSTALL,
                self.tr(
                    "Installer ou mettre à jour le Python de ScruTech (environ 1 Go, une fois)"
                ),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.GEE_KEY,
                self.tr("Clé Google Earth Engine à vérifier (.json, facultatif)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
                extension="json",
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterFile(
                    self.UV_EXE,
                    self.tr("Programme uv (si non trouvé automatiquement)"),
                    behavior=_compat.FILE_BEHAVIOR_FILE,
                    optional=True,
                )
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        feedback.pushInfo(f"QGIS {Qgis.version()}")
        ready = self._check_python(parameters, context, feedback)
        self._check_internet(feedback)
        self._check_gee(parameters, context, feedback)
        self._check_mnt(feedback)
        if ready:
            feedback.pushInfo(
                "\nScruTech est prêt : vous pouvez lancer les outils des groupes 1 à 5."
            )
        else:
            feedback.reportError(
                "\nScruTech n'est pas encore prêt : suivez les points [À FAIRE] ci-dessus.", False
            )
        return {"PRET": ready}

    # --- checks --------------------------------------------------------------
    def _check_python(self, parameters, context, feedback) -> bool:
        plugin_root = Path(__file__).resolve().parents[1]
        python_exe = _venv.find_python(plugin_root)
        report = _setup.check_env(python_exe) if python_exe else {}
        ready = bool(python_exe) and not report.get("error") and not report.get("missing")
        if not ready and self.parameterAsBool(parameters, self.INSTALL, context):
            python_exe = self._install(parameters, context, feedback, plugin_root)
            report = _setup.check_env(python_exe)
            ready = not report.get("error") and not report.get("missing")

        if ready:
            _venv.remember(python_exe)
            feedback.pushInfo(f"[OK] Python de ScruTech (Python {report['python']}) : {python_exe}")
            if not report.get("geoai"):
                feedback.pushInfo(
                    "[FACULTATIF] GeoAI (groupe 6) n'est pas installé : il demande un module "
                    "de plusieurs Go (torch). Rien à faire si vous ne l'utilisez pas."
                )
        elif not python_exe:
            feedback.reportError(
                "[À FAIRE] Le Python de ScruTech n'est pas installé. Cochez « Installer ou "
                "mettre à jour le Python de ScruTech » en haut de cette fenêtre, puis Exécuter.",
                False,
            )
        elif report.get("error"):
            feedback.reportError(
                f"[À FAIRE] Le Python trouvé ne répond pas ({python_exe}) : {report['error']}\n"
                "Cochez « Installer ou mettre à jour » puis Exécuter.",
                False,
            )
        else:
            feedback.reportError(
                "[À FAIRE] Il manque des modules dans le Python de ScruTech ("
                + ", ".join(report["missing"])
                + "). Cochez « Installer ou mettre à jour » puis Exécuter.",
                False,
            )
        return ready

    def _install(self, parameters, context, feedback, plugin_root: Path) -> str:
        uv = self.parameterAsString(parameters, self.UV_EXE, context).strip() or _setup.find_uv()
        if not uv:
            raise QgsProcessingException(_setup.UV_MISSING)
        project = _setup.engine_project(plugin_root)
        if project is None:
            raise QgsProcessingException(
                "Les sources du moteur manquent dans l'extension. Réinstallez ScruTech depuis "
                "son fichier ZIP."
            )
        feedback.pushInfo(
            f"Installation dans {_setup.USER_VENV} ({_setup.ENV_SIZE}, quelques minutes)…"
        )
        code = _setup.install_env(uv, project, feedback.pushInfo, feedback.isCanceled)
        if code == -1:
            raise QgsProcessingException("Installation annulée.")
        if code != 0:
            raise QgsProcessingException(
                f"L'installation a échoué (code {code}). Le journal ci-dessus indique pourquoi. "
                "Vérifiez la connexion internet et relancez : ce qui est déjà téléchargé est "
                "conservé."
            )
        return str(_venv._python_in(_setup.USER_VENV))

    def _check_internet(self, feedback) -> None:
        reachable = (_compat.NETWORK_NO_ERROR, _compat.NETWORK_SERVER_ERROR)
        for label, url in _SERVICES:
            request = QgsBlockingNetworkRequest()
            if request.head(QNetworkRequest(QUrl(url)), False, feedback) in reachable:
                feedback.pushInfo(f"[OK] Internet : {label}")
            else:
                feedback.reportError(
                    f"[À FAIRE] Internet : {label} injoignable ({request.errorMessage()}). "
                    "Vérifiez la connexion, le proxy (Préférences ▸ Options ▸ Réseau) ou le "
                    "pare-feu.",
                    False,
                )

    def _check_gee(self, parameters, context, feedback) -> None:
        path = self.parameterAsString(parameters, self.GEE_KEY, context).strip()
        if path:
            source = "fichier indiqué"
            key_text = ""
            try:
                key_text = Path(path).read_text(encoding="utf-8")
                problems = _setup.check_gee_key(key_text)
            except OSError as exc:
                problems = [f"fichier illisible ({exc})"]
        elif os.environ.get("SCRUTECH_GEE_CREDENTIALS"):
            source = "variable SCRUTECH_GEE_CREDENTIALS"
            key_text = os.environ["SCRUTECH_GEE_CREDENTIALS"]
            problems = _setup.check_gee_key(key_text)
        elif _setup.DEFAULT_GEE_KEY.is_file():
            source = str(_setup.DEFAULT_GEE_KEY)
            key_text = _setup.DEFAULT_GEE_KEY.read_text(encoding="utf-8")
            problems = _setup.check_gee_key(key_text)
        else:
            feedback.pushInfo(
                "[FACULTATIF] Clé Google Earth Engine : nécessaire seulement pour AlphaEarth. "
                f"Rangez-la dans {_setup.DEFAULT_GEE_KEY} pour qu'elle soit trouvée toute seule.\n"
                + _GEE_STEPS
            )
            return
        if problems:
            feedback.reportError(
                f"[À FAIRE] Clé Google Earth Engine ({source}) : "
                + " ; ".join(problems)
                + ".\n"
                + _GEE_STEPS,
                False,
            )
            return
        python_exe = _venv.find_python(Path(__file__).resolve().parents[1])
        error = _setup.check_gee_access(python_exe, key_text) if python_exe else ""
        if not python_exe:
            feedback.pushInfo(
                f"[OK] Clé Google Earth Engine ({source}) : format valide (accès testé une fois "
                "le Python de ScruTech installé)."
            )
        elif not error:
            feedback.pushInfo(f"[OK] Clé Google Earth Engine ({source}) : accès vérifié.")
        elif "serviceusage" in error.lower():
            feedback.reportError(
                f"[À FAIRE] Clé Google Earth Engine ({source}) reconnue, mais Google refuse "
                "l'accès : son compte de service n'a pas le droit d'utiliser le projet. Dans "
                "console.cloud.google.com ▸ IAM et administration ▸ IAM (projet de la clé), "
                "ajoutez au compte de service le rôle « Service Usage Consumer », puis relancez "
                "cet outil après quelques minutes.",
                False,
            )
        else:
            feedback.reportError(
                f"[À FAIRE] Clé Google Earth Engine ({source}) : Earth Engine refuse l'accès "
                f"({error}).\n" + _GEE_STEPS,
                False,
            )

    def _check_mnt(self, feedback) -> None:
        mnt = os.environ.get("SCRUTECH_MNT", "").strip()
        if not mnt:
            feedback.pushInfo(
                "[OK] MNT : rien à préparer. L'écobuage télécharge le MNT IGN de la zone tout "
                "seul (LiDAR HD, complété par le RGE ALTI), et « 1 · Préparer l'emprise ▸ MNT "
                "de la zone » le fournit aussi pour Biotrame."
            )
        elif mnt.startswith(("http://", "https://", "/vsi")) or Path(mnt).is_file():
            feedback.pushInfo(f"[OK] MNT déclaré par la variable SCRUTECH_MNT : {mnt}")
        else:
            feedback.reportError(
                f"[À FAIRE] La variable SCRUTECH_MNT pointe vers un fichier absent : {mnt}", False
            )
