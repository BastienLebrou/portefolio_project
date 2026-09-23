"""One application: its settings on the left, the map and its results on the right.

The study area is whatever the map shows, so there is no extent to type. The run streams into
the log, and the report of the zone opens in the same view when it is over.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import settings
from .catalog import Application, Field
from .engine import EngineRun
from .map_view import MapView


class RunPage(QWidget):
    """The page of one application: form, run, log, map and report."""

    needs_setup = Signal()

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.run: EngineRun | None = None
        self.report: Path | None = None
        self.controls: dict[str, QWidget] = {}

        split = QSplitter(self)
        split.addWidget(self._panel())
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(8)
        self.view = MapView()
        bar = QHBoxLayout()
        self.map_button = QPushButton("Carte")
        self.report_button = QPushButton("Rapport")
        self.report_button.setEnabled(False)
        self.map_button.clicked.connect(lambda: self.view.show_map())
        self.report_button.clicked.connect(self._show_report)
        bar.addWidget(QLabel("La zone analysée est ce que montre la carte."))
        bar.addStretch(1)
        bar.addWidget(self.map_button)
        bar.addWidget(self.report_button)
        right_box.addLayout(bar)
        right_box.addWidget(self.view, 1)
        split.addWidget(right)
        split.setSizes([380, 820])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(split)

    # --- left panel ------------------------------------------------------------
    def _panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("card")
        box = QVBoxLayout(panel)
        box.setContentsMargins(18, 18, 18, 18)
        box.setSpacing(12)
        title = QLabel(self.app.name)
        title.setObjectName("section")
        tagline = QLabel(self.app.tagline)
        tagline.setObjectName("tileText")
        tagline.setWordWrap(True)
        box.addWidget(title)
        box.addWidget(tagline)

        form = QFormLayout()
        form.setSpacing(8)
        for field in self.app.fields:
            widget = _control(field)
            self.controls[field.key] = widget
            form.addRow(field.label, widget)
        box.addLayout(form)
        if self.app.needs_vegetation:
            note = QLabel("Analysez d'abord la végétation de la zone pour obtenir les cartes.")
            note.setObjectName("tileText")
            note.setWordWrap(True)
            box.addWidget(note)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("Lancer")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("Annuler")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        box.addLayout(buttons)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        box.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        box.addWidget(self.log, 1)
        return panel

    def values(self) -> dict:
        """What the form says, ready for the engine spec."""
        out: dict = {}
        for field in self.app.fields:
            widget = self.controls[field.key]
            if isinstance(widget, QComboBox):
                out[field.key] = widget.currentData()
            elif isinstance(widget, QSpinBox | QDoubleSpinBox):
                out[field.key] = widget.value()
        return out

    # --- running ---------------------------------------------------------------
    def _start(self) -> None:
        python = settings.engine_python()
        if not python:
            self._say("Le moteur de ScruTech n'est pas installé : ouvrez la Configuration.")
            self.needs_setup.emit()
            return
        self.view.extent(lambda bbox: self._start_on(bbox, python))

    def _start_on(self, bbox, python: str) -> None:
        if bbox is None:
            self._say("La carte n'est pas encore prête : réessayez dans un instant.")
            return
        settings.set_last_extent(bbox)
        folder = settings.run_folder(self.app.key, bbox)
        folder.mkdir(parents=True, exist_ok=True)
        out = str(folder / "sortie.tif") if self.app.output == "tif" else str(folder)
        self.log.clear()
        self.report = None
        self.report_button.setEnabled(False)
        self._busy(True)
        self.run = EngineRun(python, self.app.spec(bbox, self.values(), out), self)
        self.run.progress.connect(self._on_progress)
        self.run.message.connect(self._say)
        self.run.finished.connect(self._on_finished)
        self.run.start()

    def _cancel(self) -> None:
        if self.run is not None:
            self.run.cancel()
            self._say("Calcul annulé.")

    def _on_progress(self, pct: int, _msg: str) -> None:
        if pct >= 0:
            self.progress.setValue(pct)

    def _on_finished(self, payload: dict, error: str) -> None:
        self._busy(False)
        self.run = None
        if error:
            self._say(f"Échec : {error}")
            return
        self.progress.setValue(100)
        for label, why in (payload.get("skipped") or {}).items():
            self._say(f"{label} : étape sautée. {why}")
        report = payload.get("report_path")
        if report:
            self.report = Path(report)
            self.report_button.setEnabled(True)
            self._show_report()
            self._say("Terminé : le rapport de la zone est affiché à droite.")
        else:
            self._say("Terminé. Les résultats sont enregistrés dans le dossier de la zone.")

    def _busy(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress.setValue(0 if running else self.progress.value())

    def _show_report(self) -> None:
        if self.report is not None and self.report.is_file():
            self.view.show_file(self.report)

    def _say(self, message: str) -> None:
        self.log.appendPlainText(message)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())


def _control(field: Field) -> QWidget:
    """The widget for one form field."""
    if field.kind == "choice":
        combo = QComboBox()
        for label, value in field.choices:
            combo.addItem(label, value)
        combo.setCurrentIndex(max(0, [v for _l, v in field.choices].index(field.default)))
        return combo
    if field.kind == "float":
        decimal = QDoubleSpinBox()
        decimal.setRange(float(field.minimum), float(field.maximum))
        decimal.setDecimals(1)
        decimal.setSingleStep(0.5)
        decimal.setValue(float(field.default))  # type: ignore[arg-type]
        decimal.setAlignment(Qt.AlignmentFlag.AlignRight)
        return decimal
    whole = QSpinBox()
    whole.setRange(int(field.minimum), int(field.maximum))
    whole.setValue(int(field.default))  # type: ignore[call-overload]
    whole.setAlignment(Qt.AlignmentFlag.AlignRight)
    return whole
