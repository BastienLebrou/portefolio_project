"""QGIS plugin initialization for EUDR & Climate Risk Analyzer."""


def classFactory(iface):
    """Load the plugin class required by QGIS."""
    from .eudr_analyzer_plugin import EudrClimateRiskAnalyzerPlugin

    return EudrClimateRiskAnalyzerPlugin(iface)
