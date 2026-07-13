<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.svg">
  <img src="assets/banner-light.svg" alt="Bastien Lebrou — Géomatique, ingénierie de données géospatiales, télédétection" width="100%">
</picture>

[![CI](https://github.com/BastienLebrou/portefolio_project/actions/workflows/ci.yml/badge.svg)](https://github.com/BastienLebrou/portefolio_project/actions/workflows/ci.yml)
[![Portfolio](https://github.com/BastienLebrou/portefolio_project/actions/workflows/portfolio.yml/badge.svg)](https://github.com/BastienLebrou/portefolio_project/actions/workflows/portfolio.yml)

</div>

## 🧭 À propos

Développeur **géomatique & data engineering** : j'analyse des territoires à partir de données
géospatiales — imagerie satellite, open data, cadastre — avec un objectif constant : des
**pipelines reproductibles, testés et cartographiables** plutôt que des scripts jetables.

- 🐍 Écosystème Python SIG : GeoPandas, Shapely, PostGIS, **DuckDB spatial**, GeoParquet, QGIS
- 🛰️ Télédétection & datacubes : STAC, Sentinel-2, xarray/dask, odc-stac, rasterio
- 📈 Statistiques de tendance : Mann-Kendall, pente de Sen, anomalies & VCI
- 🧪 Qualité : pytest, ruff, mypy, pre-commit, intégration continue GitHub Actions

## 🗂️ Projets

### 🌿 VegeVigie — sentinelle de la végétation

<img align="right" width="380" src="vegevigie/docs/trend_map_demo.png" alt="Carte des tendances de verdissement/brunissement produite par VegeVigie">

Pipeline de géo-ingénierie de données **reproductible** qui surveille la santé de la végétation
en Ardèche à partir d'une décennie d'images **Sentinel-2** : séries temporelles NDVI →
composites mensuels → **tendances statistiquement significatives** (Mann-Kendall + Sen) →
**stress hydrique** (anomalies, VCI) → agrégation et **classement par commune** (DuckDB +
GeoParquet) → tableau de bord.

- CLI `typer` en étapes idempotentes et cachées : `aoi → search → cube → ndvi → trend → drought → zonal`
- Noyau statistique **vectorisé** (numpy/dask), validé contre `pymannkendall`
- **60+ tests** hors-ligne, lint et CI sur chaque push
- 🧩 **ScruTech** : plugin QGIS Processing qui pilote le même moteur en un clic depuis QGIS

➡️ [Code, démos et méthodologie](vegevigie/) · [Plugin QGIS ScruTech](vegevigie/qgis_plugin/)

```mermaid
flowchart LR
    A[STAC · Sentinel-2 L2A] --> B[Datacube xarray<br/>masquage nuages SCL]
    B --> C[NDVI · composites mensuels]
    C --> D[Tendances MK + Sen]
    C --> E[Sécheresse · VCI]
    D --> F[Stats communales<br/>DuckDB · GeoParquet]
    E --> F
    F --> G[Cartes QGIS · dashboard]
```

### 🏢 Mini data centers résidentiels — sélection de sites SIG

Méthodologie et outillage de **scoring de parcelles cadastrales** pour l'implantation de mini
data centers résidentiels : filtrage spatial multi-critères (foncier, raccordement **fibre
ARCEP**, énergie, nuisances sonores, contraintes réglementaires), pensé coût d'abord et
cloud-native.

- Scripts de téléchargement **open data** (ARCEP fibre, espaces boisés classés) et d'adaptation de données réelles
- Analyse réelle multi-axes sur la commune d'**Alba-la-Romaine** avec export **GeoPackage + styles QML** prêts pour QGIS
- Architecture cible : dbt-duckdb spatial → GeoParquet partitionné → index **H3** → PMTiles

➡️ [Méthodologie, prompts SIG et outil](_data_center_sig/)

## 🔬 Analyses en images

Figures produites par le vrai code du pipeline VegeVigie (démos sur données synthétiques,
reproductibles via `vegevigie run --small`) :

<table>
  <tr>
    <td align="center" width="50%">
      <img src="vegevigie/docs/trend_map_demo.png" alt="Carte des tendances NDVI par pixel" width="100%"><br>
      <sub><b>Tendances par pixel</b> — verdissement/brunissement, Mann-Kendall + pente de Sen</sub>
    </td>
    <td align="center" width="50%">
      <img src="vegevigie/docs/drought_demo.png" alt="Carte des anomalies de sécheresse" width="100%"><br>
      <sub><b>Stress hydrique</b> — anomalies NDVI (z-score) et indice VCI</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="vegevigie/docs/commune_ranking_demo.png" alt="Classement des communes" width="100%"><br>
      <sub><b>Classement communal</b> — agrégation zonale et requêtes DuckDB</sub>
    </td>
    <td align="center" width="50%">
      <img src="vegevigie/docs/monthly_ndvi_timeseries.png" alt="Série temporelle NDVI mensuelle" width="100%"><br>
      <sub><b>Séries temporelles</b> — composites NDVI mensuels, robustes aux nuages</sub>
    </td>
  </tr>
</table>

## 📊 Statistiques du dépôt

Chiffres et graphiques **générés automatiquement toutes les 48 h** depuis l'historique Git
réel (script [`scripts/generate_stats.py`](scripts/generate_stats.py), sans dépendance externe).

<!-- AUTO-STATS:START -->
| 📦 Commits | 📅 Jours actifs | 🗂️ Projets |
|:---:|:---:|:---:|
| **22** | **7** | **2** |

| 🐍 Lignes de Python | ✅ Tests automatisés | 🥇 Langage principal |
|:---:|:---:|:---:|
| **6 268** | **62** | **Python (65,2 %)** |

*Dernière mise à jour automatique : 13 juillet 2026 à 11:57 (heure de Paris) — commit `955bbc8`.*
<!-- AUTO-STATS:END -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/activity-dark.svg">
  <img src="assets/activity-light.svg" alt="Commits par semaine sur les 26 dernières semaines" width="100%">
</picture>

<table>
  <tr>
    <td width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="assets/languages-dark.svg">
        <img src="assets/languages-light.svg" alt="Répartition des langages du dépôt" width="100%">
      </picture>
    </td>
    <td width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="assets/weekdays-dark.svg">
        <img src="assets/weekdays-light.svg" alt="Répartition des commits par jour de la semaine" width="100%">
      </picture>
    </td>
  </tr>
</table>

## 🛠️ La stack en un schéma

```mermaid
flowchart LR
    subgraph Sources
        S1[Sentinel-2 · STAC]
        S2[IGN · limites admin]
        S3[Open data<br/>ARCEP · EBC · cadastre]
    end
    subgraph Traitement
        T1[xarray · dask<br/>datacubes]
        T2[GeoPandas · Shapely]
        T3[Stats de tendance<br/>MK · Sen · VCI]
        T4[DuckDB spatial<br/>GeoParquet]
    end
    subgraph Livrables
        L1[Cartes & couches QGIS]
        L2[Classements territoriaux]
        L3[Dashboards]
        L4[Plugin QGIS ScruTech]
    end
    S1 --> T1 --> T3 --> T4
    S2 --> T2 --> T4
    S3 --> T2
    T4 --> L1 & L2 & L3
    T3 --> L4
```

## ⚙️ Automatisation du portfolio

Cette page s'entretient toute seule : un workflow GitHub Actions
([`portfolio.yml`](.github/workflows/portfolio.yml)) tourne **tous les deux jours**, régénère
statistiques et graphiques SVG (thèmes clair/sombre) depuis l'historique Git, puis committe le
résultat — un commit d'activité est créé même sans changement.

```mermaid
flowchart LR
    A([⏰ cron · 48 h]) --> B[generate_stats.py<br/>lecture de l'historique Git]
    B --> C[SVG clair/sombre<br/>+ tableau de stats]
    C --> D[Commit & push]
    D --> E([README toujours à jour])
```

## 📫 Contact

- GitHub : [@BastienLebrou](https://github.com/BastienLebrou)
- E-mail : [bastienlebrou1@gmail.com](mailto:bastienlebrou1@gmail.com)

<sub>Les statistiques et visuels de cette page sont calculés depuis l'historique Git réel du
dépôt — rien n'est saisi à la main.</sub>
