"""Configuration du POC "détection de bâtiments professionnels potentiellement vacants".

Tous les paramètres pilotables sont ici (ZONE, BUFFER_M, USAGES_CIBLE, source SIRENE,
chemins). Aucun chemin n'est codé en dur : tout est dérivé de l'emplacement du module.

Endpoints vérifiés en live le 2026-06-15 (ils bougent — voir README) :
  - WFS BD TOPO      : https://data.geopf.fr/wfs/ows  (COUNT plafonné à 5000/req)
  - recherche-entr.  : https://recherche-entreprises.api.gouv.fr/search
                       (total_results plafonné à 10000 -> partition par section NAF ;
                        per_page max = 25)
  - découpage admin. : https://geo.api.gouv.fr/communes/{insee}
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constantes méthodologiques / endpoints                                       #
# --------------------------------------------------------------------------- #

# Usages BD TOPO retenus comme "professionnels". Valeurs possibles du champ
# usage_1/usage_2 : Résidentiel, Commercial et services, Industriel, Agricole,
# Religieux, Sportif, Annexe, Indifférencié.
USAGES_CIBLE_DEFAUT: frozenset[str] = frozenset(
    {"Commercial et services", "Industriel"}
)

# Sections NAF (A..U) — 1re passe de partition de l'API pour contourner le
# plafond de 10000 résultats. Sur les grandes villes une section peut elle-même
# dépasser le cap (ex. Lyon 3e section M) -> sous-partition par code NAF (ci-dessous).
NAF_SECTIONS: tuple[str, ...] = tuple("ABCDEFGHIJKLMNOPQRSTU")

# Plages division NAF (2 chiffres) -> section (NAF rév.2). Sert à regrouper les
# codes pleins par section pour la sous-partition anti-plafond.
NAF_SECTION_RANGES: dict[str, range] = {
    "A": range(1, 4), "B": range(5, 10), "C": range(10, 34), "D": range(35, 36),
    "E": range(36, 40), "F": range(41, 44), "G": range(45, 48), "H": range(49, 54),
    "I": range(55, 57), "J": range(58, 64), "K": range(64, 67), "L": range(68, 69),
    "M": range(69, 76), "N": range(77, 83), "O": range(84, 85), "P": range(85, 86),
    "Q": range(86, 89), "R": range(90, 94), "S": range(94, 97), "T": range(97, 99),
    "U": range(99, 100),
}
NAF_DIV_TO_SECTION: dict[str, str] = {
    f"{dv:02d}": sec for sec, rg in NAF_SECTION_RANGES.items() for dv in rg
}
# ~732 codes NAF pleins (ex. "68.20A"), figés dans le package (cf. README).
# Le filtre API `activite_principale` n'accepte que ce format (dot), pas "68".
NAF_CODES_FILE: str = "naf_rev2_subclasses.json"

# Communes à arrondissements municipaux (Paris/Lyon/Marseille) : en base SIRENE,
# les établissements portent le code ARRONDISSEMENT, pas celui de la commune.
PLM_ARRONDISSEMENTS: dict[str, list[str]] = {
    "75056": [f"751{n:02d}" for n in range(1, 21)],   # Paris    75101..75120
    "13055": [f"132{n:02d}" for n in range(1, 17)],   # Marseille 13201..13216
    "69123": [f"693{n:02d}" for n in range(81, 90)],  # Lyon     69381..69389
}

WFS_URL: str = "https://data.geopf.fr/wfs/ows"
WFS_TYPENAME: str = "BDTOPO_V3:batiment"
WFS_PAGE_SIZE: int = 5000  # plafond serveur constaté (COUNT>5000 est ignoré)

REE_URL: str = "https://recherche-entreprises.api.gouv.fr/search"
REE_PER_PAGE: int = 25       # max accepté (per_page=100 -> rejeté)
REE_MAX_RESULTS: int = 10000  # plafond dur de l'API

# Base Sirene de la Métropole de Lyon (miroir data.gouv) : établissements ACTIFS
# déjà géolocalisés sur les ~59 communes de la Métropole. Source EN MASSE idéale
# pour une emprise multi-communes du Grand Lyon — évite des milliers d'appels API
# (l'emprise d'étude recoupe ~10 communes, ~180-220k établissements). the_geom =
# POINT(lon lat) WGS84 ; colonnes utiles : siret, denomination, activitenaf, insee.
GRANDLYON_SIRENE_URL: str = "https://www.data.gouv.fr/api/1/datasets/r/a28527c0-0221-41f5-a230-bbb1d50a5392"

GEOAPI_COMMUNE_URL: str = "https://geo.api.gouv.fr/communes/{insee}"
GEOAPI_COMMUNES_URL: str = "https://geo.api.gouv.fr/communes"

CRS_WGS84: int = 4326
CRS_L93: int = 2154  # Lambert-93, mètres

# Correspondance de colonnes pour le mode SIRENE "geo_file" (fichier départemental
# pré-géocodé fourni par l'utilisateur). Surchargeable si le fichier diffère.
GEOFILE_COLS_DEFAUT: dict[str, str] = {
    "siret": "siret",
    "denomination": "denominationUsuelleEtablissement",
    "activite_principale": "activitePrincipaleEtablissement",
    "etat": "etatAdministratifEtablissement",
    "latitude": "latitude",
    "longitude": "longitude",
    "code_commune": "codeCommuneEtablissement",
}


@dataclass(frozen=True)
class Config:
    """Paramètres d'une exécution. Immuable : on dérive des variantes via `with_`."""

    # --- Zone : fournir EXACTEMENT l'une des trois -------------------------- #
    zone_insee: str | None = "01053"  # code INSEE commune (défaut crash-test)
    zone_bbox: tuple[float, float, float, float] | None = None  # (minx,miny,maxx,maxy) WGS84
    zone_emprise_file: Path | None = None  # polygone d'emprise (.parquet/.gpkg/.geojson)

    # --- Méthode ----------------------------------------------------------- #
    buffer_m: float = 15.0
    usages_cible: frozenset[str] = USAGES_CIBLE_DEFAUT

    # --- Source SIRENE ----------------------------------------------------- #
    sirene_source: str = "api"           # "api" | "geo_file" | "grandlyon"
    sirene_geo_file: Path | None = None  # requis si sirene_source == "geo_file"

    # --- Infra ------------------------------------------------------------- #
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    use_cache: bool = True
    http_timeout: float = 60.0
    http_retries: int = 4
    request_pause_s: float = 0.0  # petite pause entre requêtes API (politesse)
    user_agent: str = "vacance-poc/1.0 (POC detection batiments pro vacants)"

    # --- Chemins dérivés (pas de hardcode) --------------------------------- #
    @property
    def cache_dir(self) -> Path:
        return self.base_dir / "cache"

    @property
    def output_dir(self) -> Path:
        return self.base_dir / "BDD" / "_vacance"

    @property
    def label(self) -> str:
        """Identifiant de la zone, sert de nom de dossier de sortie."""
        if self.zone_insee:
            return self.zone_insee
        if self.zone_emprise_file:
            return self.zone_emprise_file.stem
        b = self.zone_bbox or (0, 0, 0, 0)
        return "bbox_" + "_".join(f"{c:.4f}" for c in b)

    def validate(self) -> None:
        zones = [bool(self.zone_insee), bool(self.zone_bbox), bool(self.zone_emprise_file)]
        if sum(zones) != 1:
            raise ValueError(
                "Config invalide : fournir EXACTEMENT une zone "
                "(zone_insee OU zone_bbox OU zone_emprise_file)."
            )
        if self.sirene_source not in ("api", "geo_file", "grandlyon"):
            raise ValueError(f"sirene_source inconnu : {self.sirene_source!r}")
        if self.sirene_source == "geo_file" and not self.sirene_geo_file:
            raise ValueError("sirene_source='geo_file' nécessite sirene_geo_file (chemin).")
        if self.buffer_m < 0:
            raise ValueError("buffer_m doit être >= 0.")

    def with_(self, **changes) -> "Config":
        """Retourne une copie modifiée (dataclass immuable)."""
        return replace(self, **changes)
