"""One application: its settings on the left, the map and its results on the right.

The study area is picked on the map — a commune searched by name, a rectangle drawn with the
mouse, or coordinates typed in the panel — and falls back to whatever the map shows. The run
streams into the log, and the report of the zone opens in the same view when it is over.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import communes, settings
from .catalog import Application, Field
from .engine import EngineRun
from .map_view import MapView

_BASEMAPS = (
    "Plan (OpenStreetMap)",
    "Plan IGN",
    "Photographies aériennes (IGN)",
    "Relief (OpenTopoMap)",
)


class _Search(QThread):
    """The commune lookup, off the window thread so the interface never freezes."""

    done = Signal(list, str)  # communes, error message ("" when all went well)

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self._name = name

    def run(self) -> None:  # noqa: D102 — QThread API
        try:
            self.done.emit(communes.search(self._name), "")
        except Exception as exc:  # noqa: BLE001 — shown to the user, never a crash
            self.done.emit([], str(exc))


class RunPage(QWidget):
    """The page of one application: zone, form, run, log, map and report."""

    needs_setup = Signal()

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.run: EngineRun | None = None
        self.report: Path | None = None
        self.controls: dict[str, QWidget] = {}
        self._search: _Search | None = None

        self.view = MapView()
        self._showing = "map"
        split = QSplitter(self)
        split.addWidget(self._panel())
        right = QWidget()
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(8)
        bar = QHBoxLayout()
        self.basemap = QComboBox()
        self.basemap.addItems(_BASEMAPS)
        self.basemap.currentTextChanged.connect(self.view.set_basemap)
        self.map_button = QPushButton("Carte")
        self.report_button = QPushButton("Rapport")
        self.report_button.setEnabled(False)
        self.map_button.clicked.connect(self._show_map)
        self.report_button.clicked.connect(self._show_report)
        bar.addWidget(QLabel("Fond de carte"))
        bar.addWidget(self.basemap, 1)
        bar.addWidget(self.map_button)
        bar.addWidget(self.report_button)
        right_box.addLayout(bar)
        right_box.addWidget(self.view, 1)
        split.addWidget(right)
        split.setSizes([380, 820])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(split)
        # The rectangle lives in the page, so redraw it each time the map page is (re)loaded.
        self.view.loadFinished.connect(self._on_view_loaded)

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
        box.addWidget(self._zone_box())

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

    def _zone_box(self) -> QWidget:
        """Name the zone, find its commune, draw it, or type its coordinates."""
        group = QWidget()
        box = QVBoxLayout(group)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        heading = QLabel("Zone d'étude")
        heading.setObjectName("section")
        box.addWidget(heading)

        self.zone_name = QLineEdit()
        self.zone_name.setPlaceholderText("Nom de la zone (titre du rapport)")
        box.addWidget(self.zone_name)

        line = QHBoxLayout()
        self.commune_name = QLineEdit()
        self.commune_name.setPlaceholderText("Commune…")
        self.commune_name.returnPressed.connect(self._find_commune)
        self.find_button = QPushButton("Chercher")
        self.find_button.clicked.connect(self._find_commune)
        line.addWidget(self.commune_name, 1)
        line.addWidget(self.find_button)
        box.addLayout(line)
        self.results = QComboBox()
        self.results.setVisible(False)
        self.results.activated.connect(self._pick_commune)
        box.addWidget(self.results)

        tools = QHBoxLayout()
        draw = QPushButton("Dessiner")
        draw.setToolTip("Cliquez, puis tracez le rectangle de la zone sur la carte.")
        draw.clicked.connect(self.view.start_draw)
        whole = QPushButton("Toute la vue")
        whole.setToolTip("La zone redevient ce que montre la carte.")
        whole.clicked.connect(self._use_view)
        read_back = QPushButton("Relever")
        read_back.setToolTip("Recopier la zone de la carte dans les coordonnées ci-dessous.")
        read_back.clicked.connect(lambda: self.view.extent(self._fill_bbox))
        for button in (draw, whole, read_back):
            tools.addWidget(button)
        box.addLayout(tools)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.bbox: dict[str, QDoubleSpinBox] = {}
        cells = (("Ouest", 0, 0), ("Sud", 0, 2), ("Est", 1, 0), ("Nord", 1, 2))
        for label, row, column in cells:
            spin = QDoubleSpinBox()
            spin.setDecimals(5)
            limit = 180.0 if label in ("Ouest", "Est") else 90.0
            spin.setRange(-limit, limit)
            spin.setAlignment(Qt.AlignmentFlag.AlignRight)
            spin.setMinimumWidth(110)
            spin.editingFinished.connect(self._apply_bbox)
            self.bbox[label] = spin
            grid.addWidget(QLabel(label), row, column)
            grid.addWidget(spin, row, column + 1)
        box.addLayout(grid)
        saved = settings.last_extent()
        if saved:
            self._fill_bbox(saved)
        return group

    # --- zone ------------------------------------------------------------------
    def _find_commune(self) -> None:
        name = self.commune_name.text().strip()
        if not name or self._search is not None:
            return
        self.find_button.setEnabled(False)
        self._search = _Search(name, self)
        self._search.done.connect(self._on_communes)
        self._search.start()

    def _on_communes(self, found: list, error: str) -> None:
        self._search = None
        self.find_button.setEnabled(True)
        self.results.clear()
        self.results.setVisible(bool(found))
        if error:
            self._say(f"Recherche de commune impossible : {error}")
            return
        if not found:
            self._say("Aucune commune de ce nom.")
            return
        for commune in found:
            self.results.addItem(commune.label, commune)
        self._pick_commune(0)

    def _pick_commune(self, index: int) -> None:
        commune = self.results.itemData(index)
        if commune is None:
            return
        self.view.show_commune(commune.contour)
        self._fill_bbox(commune.bbox())
        if not self.zone_name.text().strip():
            self.zone_name.setText(commune.name)

    def _use_view(self) -> None:
        self.view.clear_zone()
        self.view.extent(self._fill_bbox)

    def _fill_bbox(self, bbox) -> None:
        """Show a (west, south, east, north) in the coordinate fields."""
        if bbox is None:
            return
        for label, value in zip(("Ouest", "Sud", "Est", "Nord"), bbox, strict=True):
            spin = self.bbox[label]
            spin.blockSignals(True)
            spin.setValue(float(value))
            spin.blockSignals(False)

    def _typed_bbox(self) -> tuple[float, float, float, float]:
        return tuple(self.bbox[k].value() for k in ("Ouest", "Sud", "Est", "Nord"))  # type: ignore[return-value]

    def _apply_bbox(self) -> None:
        """Edited coordinates move the rectangle on the map."""
        west, south, east, north = self._typed_bbox()
        if east > west and north > south:
            self.view.set_zone((west, south, east, north))

    def _show_map(self) -> None:
        self._showing = "map"
        self.view.show_map()

    def _on_view_loaded(self, ok: bool) -> None:
        if ok and self._showing == "map":
            self._apply_bbox()

    # --- running ---------------------------------------------------------------
    def values(self) -> dict:
        """What the form says, ready for the engine spec."""
        out: dict = {"zone_name": self.zone_name.text().strip()}
        for field in self.app.fields:
            widget = self.controls[field.key]
            if isinstance(widget, QComboBox):
                out[field.key] = widget.currentData()
            elif isinstance(widget, QSpinBox | QDoubleSpinBox):
                out[field.key] = widget.value()
        return out

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
        self._fill_bbox(bbox)
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
            self._showing = "report"
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
