"""Main QGIS plugin logic for EUDR & Climate Risk Analyzer."""

import csv
import os
import random
from contextlib import contextmanager

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsGraduatedSymbolRenderer,
    QgsPointXY,
    QgsProject,
    QgsRendererRange,
    QgsSymbol,
    QgsVectorLayer,
)

from .eudr_analyzer_dialog import EudrAnalyzerDockWidget


LATITUDE_FIELD_CANDIDATES = (
    "latitude",
    "lat",
    "supplier_latitude",
    "supplier_lat",
    "farm_latitude",
    "farm_lat",
    "site_latitude",
    "site_lat",
    "y",
)

LONGITUDE_FIELD_CANDIDATES = (
    "longitude",
    "long",
    "lon",
    "lng",
    "supplier_longitude",
    "supplier_long",
    "supplier_lon",
    "supplier_lng",
    "farm_longitude",
    "farm_lon",
    "site_longitude",
    "site_lon",
    "x",
)

SUPPLIER_ID_FIELD_CANDIDATES = (
    "supplier_id",
    "supplier",
    "id",
    "identifier",
    "farm_id",
    "site_id",
    "producer_id",
    "name",
    "supplier_name",
)

COMMODITY_FIELD_CANDIDATES = (
    "commodity",
    "raw_material",
    "material",
    "product",
    "supply_chain",
)

CSV_ENCODING_CANDIDATES = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


class EudrClimateRiskAnalyzerPlugin:
    """Bootstrap QGIS plugin for supplier risk analysis."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock_widget = None

    def initGui(self):
        """Create toolbar and menu entries."""
        self.action = QAction("EUDR & Climate Risk Analyzer", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dock_widget)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&EUDR & Climate Risk Analyzer", self.action)

    def unload(self):
        """Remove plugin UI from QGIS."""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&EUDR & Climate Risk Analyzer", self.action)
            self.action = None

        if self.dock_widget:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

    def show_dock_widget(self):
        """Show the dock widget, creating it on first use."""
        if self.dock_widget is None:
            self.dock_widget = EudrAnalyzerDockWidget(self.iface.mainWindow())
            self.dock_widget.run_analysis_requested.connect(self.run_analysis)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)

        self.dock_widget.show()
        self.dock_widget.raise_()

    def run_analysis(self):
        """Load supplier CSV, generate mock scores, style the layer, and update UI."""
        csv_path = self.dock_widget.selected_csv_path()
        raw_material = self.dock_widget.selected_raw_material()
        run_eudr = self.dock_widget.run_eudr_analysis()
        run_climate = self.dock_widget.run_climate_analysis()

        if not csv_path:
            self._show_warning("Please select a supplier CSV file.")
            return

        if not os.path.exists(csv_path):
            self._show_warning("The selected CSV file does not exist.")
            return

        if not run_eudr and not run_climate:
            self._show_warning("Select at least one analysis module.")
            return

        self.dock_widget.set_running(True)
        self.dock_widget.set_status("Reading supplier CSV...")

        try:
            supplier_rows = read_supplier_csv(csv_path)
            scored_rows = score_supplier_rows(
                supplier_rows,
                raw_material=raw_material,
                run_eudr=run_eudr,
                run_climate=run_climate,
            )
            layer = build_supplier_point_layer(scored_rows, raw_material)

            if run_eudr:
                apply_eudr_graduated_symbology(layer)

            QgsProject.instance().addMapLayer(layer)
            self.dock_widget.populate_results(scored_rows)
            self.dock_widget.set_status(
                "Analysis complete: {} supplier location(s) loaded.".format(len(scored_rows))
            )
        except Exception as exc:
            self.dock_widget.set_status("Analysis failed.")
            QMessageBox.critical(
                self.iface.mainWindow(),
                "EUDR & Climate Risk Analyzer",
                str(exc),
            )
        finally:
            self.dock_widget.set_running(False)

    def _show_warning(self, message):
        self.dock_widget.set_status(message)
        QMessageBox.warning(
            self.iface.mainWindow(),
            "EUDR & Climate Risk Analyzer",
            message,
        )


def read_supplier_csv(csv_path):
    """Read suppliers from CSV using Python stdlib, independent of QGIS I/O."""
    with open_csv_with_fallback(csv_path) as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("The CSV file has no header row.")

        latitude_field = find_field(reader.fieldnames, LATITUDE_FIELD_CANDIDATES)
        longitude_field = find_field(reader.fieldnames, LONGITUDE_FIELD_CANDIDATES)
        supplier_id_field = find_field(reader.fieldnames, SUPPLIER_ID_FIELD_CANDIDATES)
        commodity_field = find_field(reader.fieldnames, COMMODITY_FIELD_CANDIDATES)

        if not latitude_field or not longitude_field:
            raise ValueError(
                "Could not detect latitude/longitude columns. "
                "Supported names include latitude/lat/y and longitude/lon/lng/x."
            )

        suppliers = []
        for row_number, raw_row in enumerate(reader, start=1):
            latitude = parse_coordinate(raw_row.get(latitude_field), "latitude", row_number)
            longitude = parse_coordinate(raw_row.get(longitude_field), "longitude", row_number)
            supplier_id = build_supplier_id(raw_row, supplier_id_field, row_number)

            suppliers.append(
                {
                    "source_row": row_number,
                    "supplier_id": supplier_id,
                    "source_commodity": read_optional_value(raw_row, commodity_field),
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

    if not suppliers:
        raise ValueError("The CSV file contains no supplier rows.")

    return suppliers


@contextmanager
def open_csv_with_fallback(csv_path):
    """Open CSV files exported from common tools, including Excel on Windows."""
    last_error = None

    for encoding in CSV_ENCODING_CANDIDATES:
        try:
            csv_file = open(csv_path, newline="", encoding=encoding)
            try:
                csv_file.read(4096)
                csv_file.seek(0)
                yield csv_file
                return
            finally:
                csv_file.close()
        except UnicodeDecodeError as exc:
            last_error = exc

    raise ValueError(
        "Could not read CSV encoding. Tried: {}. Last error: {}".format(
            ", ".join(CSV_ENCODING_CANDIDATES),
            last_error,
        )
    )


def find_field(fieldnames, candidates):
    """Find a CSV field by comparing normalized names against candidates."""
    normalized_lookup = {normalize_field_name(name): name for name in fieldnames}
    for candidate in candidates:
        field = normalized_lookup.get(normalize_field_name(candidate))
        if field:
            return field
    return None


def normalize_field_name(field_name):
    """Normalize a field name for tolerant CSV schema matching."""
    return str(field_name).strip().lower().replace(" ", "_").replace("-", "_")


def parse_coordinate(value, coordinate_name, row_number):
    """Parse a latitude or longitude value with clear row-level errors."""
    if value is None or str(value).strip() == "":
        raise ValueError("Missing {} on CSV row {}.".format(coordinate_name, row_number))

    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        raise ValueError(
            "Invalid {} value '{}' on CSV row {}.".format(coordinate_name, value, row_number)
        )


def build_supplier_id(raw_row, supplier_id_field, row_number):
    """Use a supplier identifier from CSV when present, otherwise generate one."""
    if supplier_id_field:
        value = str(raw_row.get(supplier_id_field, "")).strip()
        if value:
            return value

    return "SUP-{0:06d}".format(row_number)


def read_optional_value(raw_row, field_name):
    """Read an optional CSV value and return None when the field is missing."""
    if not field_name:
        return None

    value = str(raw_row.get(field_name, "")).strip()
    return value or None


def score_supplier_rows(supplier_rows, raw_material, run_eudr=True, run_climate=True):
    """Assign mock risk scores to supplier rows.

    This function is intentionally QGIS-independent so it can later be replaced
    by a real API client, local model, or AI agent workflow.
    """
    scored_rows = []
    for row in supplier_rows:
        scored_row = dict(row)
        scored_row["raw_material"] = resolve_raw_material(row, raw_material)
        scored_row["eudr_risk_score"] = random.randint(0, 100) if run_eudr else None
        scored_row["climate_risk_score"] = random.randint(0, 100) if run_climate else None
        scored_rows.append(scored_row)

    return scored_rows


def resolve_raw_material(row, selected_raw_material):
    """Use CSV commodity values when requested, otherwise use the UI fallback."""
    if selected_raw_material == "Use CSV COMMODITY column" and row.get("source_commodity"):
        return row["source_commodity"]

    if selected_raw_material == "Use CSV COMMODITY column":
        return "Unknown"

    return selected_raw_material


def build_supplier_point_layer(scored_rows, raw_material):
    """Create an in-memory WGS84 point layer from scored supplier rows."""
    layer_name = "EUDR Climate Risk - {}".format(raw_material)
    layer = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    provider = layer.dataProvider()

    provider.addAttributes(
        [
            QgsField("supplier_id", QVariant.String),
            QgsField("raw_material", QVariant.String),
            QgsField("source_row", QVariant.Int),
            QgsField("eudr_risk_score", QVariant.Int),
            QgsField("climate_risk_score", QVariant.Int),
        ]
    )
    layer.updateFields()

    features = []
    for row in scored_rows:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(row["longitude"], row["latitude"]))
        )
        feature.setAttributes(
            [
                row["supplier_id"],
                row["raw_material"],
                row["source_row"],
                row["eudr_risk_score"],
                row["climate_risk_score"],
            ]
        )
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()

    for index, feature in enumerate(layer.getFeatures()):
        scored_rows[index]["feature_id"] = feature.id()

    return layer


def apply_eudr_graduated_symbology(layer):
    """Apply green/yellow/red graduated symbology to EUDR risk score."""
    ranges = [
        build_symbol_range(layer, 0, 19, QColor("#2e7d32"), "Low EUDR risk (< 20)"),
        build_symbol_range(layer, 20, 50, QColor("#f9a825"), "Medium EUDR risk (20-50)"),
        build_symbol_range(layer, 51, 100, QColor("#c62828"), "High EUDR risk (> 50)"),
    ]

    renderer = QgsGraduatedSymbolRenderer("eudr_risk_score", ranges)
    renderer.setMode(QgsGraduatedSymbolRenderer.Custom)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def build_symbol_range(layer, lower_value, upper_value, color, label):
    """Create a QgsRendererRange with a simple marker symbol."""
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(color)
    symbol.setSize(3.5)
    return QgsRendererRange(lower_value, upper_value, symbol, label)
