"""Dock widget UI for the EUDR & Climate Risk Analyzer plugin.

The UI is defined entirely in Python so the plugin can be tested without a
Qt Designer .ui file.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class EudrAnalyzerDockWidget(QDockWidget):
    """Simple dockable panel for selecting inputs and displaying results."""

    run_analysis_requested = pyqtSignal()

    RAW_MATERIALS = (
        "Use CSV COMMODITY column",
        "Coffee",
        "Cocoa",
        "Wood",
        "Soy",
        "Palm Oil",
        "Cattle",
        "Rubber",
    )

    def __init__(self, parent=None):
        super().__init__("EUDR & Climate Risk Analyzer", parent)
        self.setObjectName("EudrClimateRiskAnalyzerDockWidget")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        container = QWidget(self)
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        input_group = QGroupBox("Supplier input", container)
        input_layout = QFormLayout(input_group)
        input_layout.setLabelAlignment(Qt.AlignLeft)

        file_picker_layout = QHBoxLayout()
        self.csv_path_edit = QLineEdit(input_group)
        self.csv_path_edit.setPlaceholderText("Select supplier CSV with latitude/longitude columns")
        self.csv_path_edit.setReadOnly(True)

        self.browse_button = QPushButton("Browse...", input_group)
        file_picker_layout.addWidget(self.csv_path_edit, stretch=1)
        file_picker_layout.addWidget(self.browse_button)
        input_layout.addRow("CSV file", file_picker_layout)

        self.raw_material_combo = QComboBox(input_group)
        self.raw_material_combo.addItems(self.RAW_MATERIALS)
        input_layout.addRow("Raw material", self.raw_material_combo)

        analysis_group = QGroupBox("Analysis modules", container)
        analysis_layout = QVBoxLayout(analysis_group)

        self.eudr_checkbox = QCheckBox("Run EUDR Deforestation Analysis", analysis_group)
        self.eudr_checkbox.setChecked(True)
        self.climate_checkbox = QCheckBox("Run 2050 Climate Stress Analysis", analysis_group)
        self.climate_checkbox.setChecked(True)

        analysis_layout.addWidget(self.eudr_checkbox)
        analysis_layout.addWidget(self.climate_checkbox)

        self.run_button = QPushButton("Run Analysis", container)

        results_label = QLabel("Results", container)
        self.results_table = QTableWidget(container)
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(
            ("Supplier ID", "Feature ID", "EUDR Risk", "Climate Risk")
        )
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setAlternatingRowColors(True)

        self.status_label = QLabel("Ready", container)
        self.status_label.setWordWrap(True)

        main_layout.addWidget(input_group)
        main_layout.addWidget(analysis_group)
        main_layout.addWidget(self.run_button)
        main_layout.addWidget(results_label)
        main_layout.addWidget(self.results_table, stretch=1)
        main_layout.addWidget(self.status_label)

        self.setWidget(container)

    def _connect_signals(self):
        self.browse_button.clicked.connect(self._select_csv_file)
        self.run_button.clicked.connect(self.run_analysis_requested.emit)

    def _select_csv_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select supplier coordinate CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if path:
            self.csv_path_edit.setText(path)

    def selected_csv_path(self):
        """Return the selected CSV path."""
        return self.csv_path_edit.text().strip()

    def selected_raw_material(self):
        """Return the selected raw material."""
        return self.raw_material_combo.currentText()

    def run_eudr_analysis(self):
        """Return True when the EUDR module is enabled."""
        return self.eudr_checkbox.isChecked()

    def run_climate_analysis(self):
        """Return True when the climate stress module is enabled."""
        return self.climate_checkbox.isChecked()

    def set_status(self, message):
        """Display a short status message in the dock."""
        self.status_label.setText(message)

    def set_running(self, running):
        """Enable or disable controls while an analysis is running."""
        self.run_button.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.raw_material_combo.setEnabled(not running)
        self.eudr_checkbox.setEnabled(not running)
        self.climate_checkbox.setEnabled(not running)

    def populate_results(self, rows):
        """Populate the results table from analysis row dictionaries."""
        self.results_table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.results_table.insertRow(row_index)
            values = (
                row.get("supplier_id", ""),
                row.get("feature_id", ""),
                self._format_score(row.get("eudr_risk_score")),
                self._format_score(row.get("climate_risk_score")),
            )

            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self.results_table.setItem(row_index, column_index, item)

    @staticmethod
    def _format_score(value):
        if value is None:
            return "Not run"
        return value
