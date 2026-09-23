"""Configuration: the engine, the data folder and the Earth Engine key, in one page.

Everything a first run needs. The engine itself is the shared ``~/.scrutech/venv`` that the
QGIS plugin also uses, built here with the very same code (``engine_env``), so configuring
ScruTech once configures both.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import engine_env
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import settings


class _Work(QThread):
    """A slow job (install, check) off the window thread, its lines streamed as they come."""

    line = Signal(str)
    done = Signal(str)  # "" when all went well

    def __init__(self, job: Callable[[Callable[[str], None]], str], parent=None) -> None:
        super().__init__(parent)
        self._job = job

    def run(self) -> None:  # noqa: D102 — QThread API
        try:
            self.done.emit(self._job(self.line.emit))
        except Exception as exc:  # noqa: BLE001 — shown to the user, never a crash
            self.done.emit(str(exc))


class ConfigPage(QWidget):
    """Engine, data folder and Earth Engine key."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._work: _Work | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 8, 24, 24)
        box.setSpacing(14)

        self.engine_label = QLabel()
        self.geoai = QCheckBox("Ajouter GeoAI (Segment Anything, environ 1 Go de plus)")
        self.install_button = QPushButton("Installer ou mettre à jour le moteur")
        self.install_button.setObjectName("primary")
        self.install_button.clicked.connect(self._install)
        choose_python = QPushButton("Choisir un Python…")
        choose_python.clicked.connect(self._choose_python)
        box.addWidget(
            _card(
                "Moteur de calcul",
                "Un Python à part, installé une fois (environ 1 Go), qui fait tourner les "
                "analyses. ScruTech ne touche pas à votre système.",
                [self.engine_label, self.geoai],
                [self.install_button, choose_python],
            )
        )

        self.data_label = QLabel()
        choose_data = QPushButton("Choisir le dossier…")
        choose_data.clicked.connect(self._choose_data)
        box.addWidget(
            _card(
                "Dossier des analyses",
                "Les résultats et le cache des zones déjà calculées.",
                [self.data_label],
                [choose_data],
            )
        )

        self.key_label = QLabel()
        choose_key = QPushButton("Choisir la clé (.json)…")
        choose_key.clicked.connect(self._choose_key)
        box.addWidget(
            _card(
                "Clé Google Earth Engine",
                "Facultative : elle sert uniquement à l'analyse des changements (AlphaEarth).",
                [self.key_label],
                [choose_key],
            )
        )

        check = QPushButton("Vérifier l'installation")
        check.clicked.connect(self._check)
        row = QHBoxLayout()
        row.addWidget(check)
        row.addStretch(1)
        box.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        box.addWidget(self.log, 1)
        self.refresh()

    def refresh(self) -> None:
        python = settings.engine_python()
        self.engine_label.setText(
            f"Moteur installé : {python}" if python else "Moteur non installé."
        )
        self.install_button.setText(
            "Mettre à jour le moteur" if python else "Installer le moteur (environ 1 Go)"
        )
        self.data_label.setText(f"Dossier : {settings.data_root()}")
        key = engine_env.DEFAULT_GEE_KEY
        self.key_label.setText(
            f"Clé enregistrée : {key}" if key.is_file() else "Aucune clé enregistrée."
        )

    # --- actions ---------------------------------------------------------------
    def _choose_python(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Python de ScruTech", "", "python*")
        if path:
            settings.set_engine_python(path)
            self.refresh()
            self.changed.emit()

    def _choose_data(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Dossier des analyses")
        if path:
            settings.set_data_root(path)
            self.refresh()

    def _choose_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Clé Google Earth Engine", "", "*.json")
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8")
        problems = engine_env.check_gee_key(text)
        if problems:
            self._say("Clé refusée : " + " ; ".join(problems))
            return
        saved = engine_env.save_gee_key(text)
        self._say(f"Clé enregistrée : {saved or engine_env.DEFAULT_GEE_KEY}")
        self.refresh()

    def _install(self) -> None:
        project = _engine_project()
        if project is None:
            self._say(
                "Les sources du moteur sont introuvables : gardez le dossier ScruTech complet."
            )
            return
        geoai = self.geoai.isChecked()

        def job(say: Callable[[str], None]) -> str:
            uv = engine_env.find_uv() or engine_env.download_uv(say)
            say(f"Installation dans {engine_env.USER_VENV} ({engine_env.ENV_SIZE})…")
            code = engine_env.install_env(uv, project, say, lambda: False, geoai)
            if code != 0:
                return f"L'installation s'est arrêtée (code {code})."
            report = engine_env.check_env(settings.engine_python())
            missing = report.get("missing") or []
            return f"Modules manquants : {', '.join(missing)}" if missing else ""

        self._start(job, "Installation du moteur…")

    def _check(self) -> None:
        python = settings.engine_python()
        if not python:
            self._say("Moteur non installé : cliquez sur « Installer le moteur ».")
            return

        def job(say: Callable[[str], None]) -> str:
            report = engine_env.check_env(python)
            if report.get("error"):
                return str(report["error"])
            say(f"Python {report.get('python')} : {python}")
            say("GeoAI installé." if report.get("geoai") else "GeoAI non installé (facultatif).")
            key = engine_env.DEFAULT_GEE_KEY
            if key.is_file():
                error = engine_env.check_gee_access(python, key.read_text(encoding="utf-8"))
                say("Clé Earth Engine : accès vérifié." if not error else f"Earth Engine : {error}")
            missing = report.get("missing") or []
            return f"Modules manquants : {', '.join(missing)}" if missing else ""

        self._start(job, "Vérification…")

    def _start(self, job, title: str) -> None:
        if self._work is not None:
            return
        self.log.clear()
        self._say(title)
        self.install_button.setEnabled(False)
        self._work = _Work(job, self)
        self._work.line.connect(self._say)
        self._work.done.connect(self._finished)
        self._work.start()

    def _finished(self, error: str) -> None:
        self._work = None
        self.install_button.setEnabled(True)
        self._say(error if error else "Tout est prêt.")
        self.refresh()
        self.changed.emit()

    def _say(self, message: str) -> None:
        self.log.appendPlainText(message.rstrip())
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())


def _engine_project() -> Path | None:
    """The engine sources shipped with ScruTech (or the repo in development)."""
    here = Path(__file__).resolve()
    for candidate in (
        here.parent / "engine" / "vegevigie",
        here.parents[4] / "packages" / "vegevigie",
    ):
        if (candidate / "pyproject.toml").is_file() and (candidate / "uv.lock").is_file():
            return candidate
    return None


def _card(title: str, text: str, labels: list[QWidget], buttons: list[QWidget]) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    box = QVBoxLayout(card)
    box.setContentsMargins(18, 16, 18, 16)
    box.setSpacing(8)
    heading = QLabel(title)
    heading.setObjectName("section")
    explain = QLabel(text)
    explain.setObjectName("tileText")
    explain.setWordWrap(True)
    box.addWidget(heading)
    box.addWidget(explain)
    for label in labels:
        box.addWidget(label)
    row = QHBoxLayout()
    for button in buttons:
        row.addWidget(button)
    row.addStretch(1)
    box.addLayout(row)
    return card
