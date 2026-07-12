"""Helper algorithm: load French commune boundaries as a zones layer.

Gives the user a ready-made polygon layer to feed the *Zones* input of
"Analyze extent" / "5 — Zonal statistics" (for per-commune ranking).

Implemented **entirely with the QGIS API** (network request + OGR GeoJSON
reader): no Python dependency and no external interpreter needed, and any
French département works. Primary source is the official
``geo.api.gouv.fr`` (IGN Admin Express); the community *france-geojson*
mirror on GitHub is used as a fallback when the API is unreachable.
"""

from __future__ import annotations

import json
import unicodedata

from qgis.core import (
    QgsFeatureSink,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterString,
    QgsProcessingUtils,
    QgsVectorLayer,
)

from .base import ScruTechAlgorithmBase

GEO_API_URL = (
    "https://geo.api.gouv.fr/departements/{dept}/communes"
    "?format=geojson&geometry=contour&fields=nom,code"
)
MIRROR_BASE = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master"
MIRROR_INDEX_URL = f"{MIRROR_BASE}/departements.geojson"
MIRROR_COMMUNES_URL = f"{MIRROR_BASE}/departements/{{slug}}/communes-{{slug}}.geojson"


def _http_get(url: str) -> bytes:
    """GET ``url`` through QGIS's network stack (proxy-aware, no extra deps)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    blocking = QgsBlockingNetworkRequest()
    if blocking.get(QNetworkRequest(QUrl(url))) != QgsBlockingNetworkRequest.NoError:
        raise RuntimeError(blocking.errorMessage() or f"request failed: {url}")
    reply = blocking.reply()
    status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
    if status is not None and int(status) >= 400:
        raise RuntimeError(f"HTTP {int(status)} for {url}")
    return bytes(reply.content())


def _slugify(name: str) -> str:
    """france-geojson path slug: accents stripped, apostrophes/spaces to hyphens."""
    decomposed = unicodedata.normalize("NFD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    return ascii_name.lower().replace("'", "-").replace(" ", "-")


def _normalize_dept(raw: str) -> str:
    dept = raw.strip().upper()
    if dept.isdigit() and len(dept) == 1:
        dept = f"0{dept}"  # "7" -> "07"
    if not dept:
        raise QgsProcessingException("Empty département code.")
    return dept


class LoadCommunesAlgorithm(ScruTechAlgorithmBase):
    """Download a département's commune polygons into a zones layer."""

    DEPARTEMENT = "DEPARTEMENT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "load_communes"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("Load commune boundaries (zones)")

    def group(self) -> str:
        return self.tr("Data")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "data"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Download the commune polygons of any French département (e.g. 07 for "
            "Ardèche, 2A for Corse-du-Sud) to use as the Zones input of 'Analyze "
            "extent' or '5 — Zonal statistics'. Uses geo.api.gouv.fr with a GitHub "
            "mirror fallback; needs internet access but no Python dependencies."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.addParameter(
            QgsProcessingParameterString(
                self.DEPARTEMENT, self.tr("Département code"), defaultValue="07"
            )
        )
        self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.tr("Communes")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        dept = _normalize_dept(self.parameterAsString(parameters, self.DEPARTEMENT, context))
        geojson = self._fetch_geojson(dept, feedback)

        path = QgsProcessingUtils.generateTempFilename(f"communes_{dept.lower()}.geojson")
        with open(path, "wb") as fh:
            fh.write(geojson)
        layer = QgsVectorLayer(path, f"communes_{dept}", "ogr")
        if not layer.isValid() or layer.featureCount() == 0:
            raise QgsProcessingException(
                self.tr("Downloaded data for département {} is empty or unreadable.").format(dept)
            )

        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, layer.fields(), layer.wkbType(), layer.crs()
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))
        total = layer.featureCount()
        for i, feature in enumerate(layer.getFeatures()):
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Canceled."))
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(100 * (i + 1) / total))
        feedback.pushInfo(self.tr("Loaded {} communes for département {}.").format(total, dept))
        return {self.OUTPUT: dest_id}

    # --- data sources ----------------------------------------------------------
    def _fetch_geojson(self, dept: str, feedback: QgsProcessingFeedback) -> bytes:
        primary = GEO_API_URL.format(dept=dept)
        feedback.pushInfo(self.tr("Fetching communes from {}…").format(primary))
        try:
            return _http_get(primary)
        except RuntimeError as exc:
            feedback.pushWarning(
                self.tr("geo.api.gouv.fr failed ({}); trying the GitHub mirror…").format(exc)
            )
        try:
            return self._fetch_from_mirror(dept, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(
                self.tr(
                    "Could not download communes for département {} from geo.api.gouv.fr "
                    "nor the france-geojson mirror: {}"
                ).format(dept, exc)
            ) from exc

    def _fetch_from_mirror(self, dept: str, feedback: QgsProcessingFeedback) -> bytes:
        """Resolve the département name from the mirror index, then fetch its communes."""
        index = json.loads(_http_get(MIRROR_INDEX_URL).decode("utf-8"))
        name = next(
            (
                f["properties"]["nom"]
                for f in index.get("features", [])
                if str(f["properties"].get("code", "")).upper() == dept
            ),
            None,
        )
        if name is None:
            raise RuntimeError(f"unknown département code {dept!r}")
        # Mirror slugs keep the code verbatim ("07-ardeche", "2A-corse-du-sud").
        slug = f"{dept}-{_slugify(name)}"
        url = MIRROR_COMMUNES_URL.format(slug=slug)
        feedback.pushInfo(self.tr("Fetching communes from {}…").format(url))
        return _http_get(url)
