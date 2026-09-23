"""The ScruTech application library: one entry per application, no GUI import.

An application is a tile in the library and a form: its ``fields`` become the form, and the
form plus the map extent become the JSON spec the engine runs (the same specs the QGIS plugin
sends). Adding a project means adding an entry here, nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    """One form control: ``key`` is the name the engine expects in the spec."""

    key: str
    label: str
    kind: str = "int"  # int | float | choice
    default: object = 0
    minimum: float = 0
    maximum: float = 0
    choices: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Application:
    """A tile of the library: what it does, and what the engine must run."""

    key: str
    name: str
    tagline: str
    icon: str
    task: str
    fields: tuple[Field, ...] = ()
    output: str = "folder"  # folder | tif
    needs_vegetation: bool = False  # reads the zone's VegeVigie analysis from the cache

    def spec(self, bbox: tuple[float, float, float, float], values: dict, out: str) -> dict:
        """The engine spec for a run: the extent, the form values and where to write."""
        key = "out_path" if self.output == "tif" else "out_folder"
        return {"task": self.task, "bbox": list(bbox), **values, key: out}


_YEARS = (
    Field("start", "Année de début", "int", 2020, 2016, 2035),
    Field("end", "Année de fin", "int", 2025, 2016, 2035),
)
_PIXEL = Field("resolution", "Précision : taille du pixel (m)", "int", 30, 10, 200)
_HEXAGONS = Field(
    "hexagons",
    "Précision de Biotrame : taille des hexagones",
    "choice",
    8,
    choices=(
        ("Grands (≈ 5 km²)", 7),
        ("Moyens (≈ 70 ha)", 8),
        ("Fins (≈ 10 ha)", 9),
        ("Très fins (≈ 1,5 ha)", 10),
    ),
)

APPLICATIONS: tuple[Application, ...] = (
    Application(
        "diagnostic",
        "Diagnostic complet",
        "Toutes les analyses de la zone à la suite, puis le rapport de synthèse.",
        "vegevigie",
        "diagnostic",
        (*_YEARS, _PIXEL, _HEXAGONS),
    ),
    Application(
        "vegevigie",
        "Végétation",
        "Tendance, rupture et sécheresse de la végétation (Sentinel-2).",
        "vegevigie",
        "vegevigie_analyze",
        (*_YEARS, _PIXEL, Field("max_cloud", "Nuages maximum par image (%)", "int", 60, 0, 100)),
    ),
    Application(
        "paff",
        "Interface habitat-forêt",
        "La frontière entre forêt et habitations, et la bande à débroussailler.",
        "paf",
        "paf_interface_aoi",
        (Field("contact_m", "Distance de contact (m)", "float", 50.0, 0, 500),),
    ),
    Application(
        "ecobuage",
        "Aptitude à l'écobuage",
        "Pente, accès et exclusions : où le brûlage dirigé est envisageable.",
        "ecobuage",
        "ecobuage_aoi",
        (Field("resolution", "Précision : taille du pixel (m)", "int", 25, 5, 200),),
    ),
    Application(
        "biotrame",
        "Priorisation écologique",
        "Réservoirs, continuités et zones humides en hexagones de priorité.",
        "vegevigie",
        "biotrame_aoi",
        (_HEXAGONS,),
    ),
    Application(
        "projection",
        "Projection climatique",
        "Le climat de la zone en 2035, 2040, 2045 et 2055, et les secteurs exposés.",
        "vegevigie",
        "projection",
        (),
        needs_vegetation=True,
    ),
    Application(
        "mnt",
        "MNT de la zone",
        "Le modèle numérique de terrain de l'IGN (LiDAR HD, RGE ALTI).",
        "data",
        "mnt_aoi",
        (Field("resolution", "Taille des pixels (m)", "float", 5.0, 0.5, 100),),
        output="tif",
    ),
    Application(
        "ortho",
        "Image aérienne",
        "La photographie aérienne de l'IGN, prête pour la segmentation.",
        "data",
        "ortho_aoi",
        (Field("resolution", "Taille des pixels (m)", "float", 0.5, 0.2, 20),),
        output="tif",
    ),
)

BY_KEY: dict[str, Application] = {app.key: app for app in APPLICATIONS}
