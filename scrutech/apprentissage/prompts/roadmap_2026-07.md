# ROADMAP — ScruTech

> Feuille de route des features, organisée par pilier sur le socle commun.
> Chaque milestone est un incrément livrable et testé. Applique ponytail à chacun :
> le plus petit incrément qui apporte de la valeur réelle. **Valide le périmètre de
> chaque milestone avec Bastien avant de l'attaquer.**

---

## Socle commun (backbone) — prérequis des 3 piliers

| # | Milestone | Contenu |
|---|-----------|---------|
| S0 | **Acquisition STAC** | Requête Planetary Computer, filtrage cloud, découpe AOI (polygone d'emprise, pas bbox), cache local GeoParquet |
| S1 | **Moteur analytique DuckDB** | Agrégation raster→vecteur, jointures spatiales, écriture GeoParquet (ZSTD, tri par identifiant) |
| S2 | **Stockage PostGIS territorial** | Schéma par territoire, table centrale d'entités, upsert-only (jamais DELETE+INSERT) |
| S3 | **Couche de restitution** | Base Streamlit + leafmap réutilisable par les 3 piliers |

Le socle se construit **une fois** et sert les trois piliers. Ne le duplique pas.

---

## Pilier 1 — VegeVigie 🌱

| # | Milestone | Contenu |
|---|-----------|---------|
| V1 | Séries NDVI | Extraction NDVI Sentinel-2, masquage nuages, série temporelle par pixel |
| V2 | Détection de tendance | Mann-Kendall + pente de Sen par pixel |
| V3 | Anomalie de stress | VCI (Vegetation Condition Index), détection de sécheresse |
| V4 | Agrégation communale | DuckDB → communes, GeoParquet |
| V5 | Dashboard | Streamlit + leafmap, sélection AOI, export |

AOI de démonstration par défaut : Ardèche (dept 07).

---

## Pilier 2 — PAF (protection feux de forêt) 🔥

| # | Milestone | Contenu |
|---|-----------|---------|
| P1 | Couche combustible | État de la végétation / biomasse sèche dérivé des indices spectraux |
| P2 | Facteur topographique | Pente, exposition, effet de versant (accélérateur de propagation) |
| P3 | Indice de risque composite | Combinaison combustible × sécheresse (VCI de VegeVigie) × topo × exposition |
| P4 | Zones de risque | Vectorisation des zones prioritaires, seuils paramétrables |
| P5 | Restitution PAF | Carte de risque + fiche territoire, export QGIS/PDF |

**Doute de continuité à lever avec Bastien avant P3** : quelle méthode de scoring du
risque (indice existant type IFM/FWI, ou scoring maison pondéré) ? Ça structure tout le pilier.

---

## Pilier 3 — Mini data centers 🖥️

| # | Milestone | Contenu |
|---|-----------|---------|
| D1 | Données réseau | Ingestion open data raccordement (postes, lignes) |
| D2 | Distance au raccordement | Calcul de proximité / coût de raccordement par site candidat |
| D3 | Contraintes spatiales | Croisement zonage, servitudes, contraintes d'implantation |
| D4 | Score de faisabilité | Score composite d'aptitude d'un site à accueillir un mini data center |
| D5 | Restitution | Carte + fiche site |

**Doute de continuité à lever avant D1** : périmètre géographique de départ et source
open data de raccordement retenue.

---

## Transverse

- **Frontend géolibre public** : vitrine open-data, démonstrateur VegeVigie en accès libre.
- **Plugin QGIS** : voir `QGIS_PLUGIN.md`. **Cible arrêtée (décision Bastien, 2026-07-08)** :
  un **plugin unique** qui intègre à terme les fonctions des **trois piliers** (VegeVigie,
  PAF, mini data centers). Pas de fusion précipitée : le plugin fonctionnel actuel
  (`vegevigie/qgis_plugin/`, piloté par le moteur partagé) reste la base v1 ; le scaffold
  pédagogique QGIS 4.0 (`scrutech/`) est la spec v2. On y branche PAF puis data centers
  au fur et à mesure que chaque pilier se stabilise sur le socle commun.
- **Agents OpenClaw** : voir `AGENTS.md` (un agent d'acquisition, un de traitement, un de restitution).

---

## Principe de séquencement

1. Socle commun d'abord (S0→S3).
2. VegeVigie ensuite (le plus mature, sert de démonstrateur public).
3. PAF réutilise le VCI de VegeVigie → à enchaîner après V3.
4. Mini data centers en parallèle possible (dépend surtout du socle, pas des indices végétation).

Ne commence jamais un pilier sans que le socle dont il dépend soit stabilisé et testé.
