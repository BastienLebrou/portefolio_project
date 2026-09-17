"""Load engine outputs into the QGIS project with their ScruTech style really applied.

Processing loads result layers without reading a sidecar ``.qml``: the styles written next to
the GeoTIFFs were silently ignored and the layers came up grey. A layer post-processor applies
the style once the layer exists in the project.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from qgis.core import QgsProcessingContext, QgsProcessingLayerPostProcessorInterface

# QGIS does not own these Python objects: keep them alive until the layers are loaded.
# ponytail: one small object per styled layer per run, fine for a desktop session.
_KEEP: list[QgsProcessingLayerPostProcessorInterface] = []


class _ApplyStyle(QgsProcessingLayerPostProcessorInterface):
    def __init__(self, qml_path: str) -> None:
        super().__init__()
        self.qml_path = qml_path

    def postProcessLayer(self, layer, context, feedback) -> None:  # noqa: N802 — QGIS API name
        if layer is None or not layer.isValid():
            return
        message, ok = layer.loadNamedStyle(self.qml_path)
        if not ok and feedback is not None:
            feedback.pushInfo(f"Style non appliqué à « {layer.name()} » : {message}")
        layer.triggerRepaint()


def queue_layer(
    context: QgsProcessingContext, path: str | Path, label: str, qml: str | None = None
) -> None:
    """Load ``path`` when the tool ends, styled by ``qml`` or by an existing sidecar ``.qml``."""
    qml_path = Path(path).with_suffix(".qml")
    if qml is not None:
        qml_path.write_text(qml, encoding="utf-8")
    details = QgsProcessingContext.LayerDetails(label, context.project(), label)
    details.forceName = True  # else Processing's "use file name" setting shows the raw file name
    if qml_path.is_file():
        post = _ApplyStyle(str(qml_path))
        _KEEP.append(post)
        details.setPostProcessor(post)
    context.addLayerToLoadOnCompletion(str(path), details)


def style_output(context: QgsProcessingContext, dest_id: str, qml: str) -> None:
    """Style an output Processing loads itself (sink or raster destination, maybe in memory)."""
    if not context.willLoadLayerOnCompletion(dest_id):
        return
    # ponytail: one small .qml per styled output left in the temp folder, the OS cleans it.
    with tempfile.NamedTemporaryFile("w", suffix=".qml", delete=False, encoding="utf-8") as f:
        f.write(qml)
    post = _ApplyStyle(f.name)
    _KEEP.append(post)
    context.layerToLoadOnCompletionDetails(dest_id).setPostProcessor(post)
