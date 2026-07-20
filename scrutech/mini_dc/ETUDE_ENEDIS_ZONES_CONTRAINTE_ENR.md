# Étude de faisabilité — Intégrer les « zones de contrainte projets ENR » d'Enedis dans l'outil map

**Source étudiée :** <https://openservices.enedis.fr/service/carte-zones-contrainte-projets-enr/>
**Date :** 2026-07-20 · **Statut :** étude préalable (pas d'implémentation dans ce dépôt)

> ⚠️ Portée. L'« outil map » visé **n'est pas dans ce dépôt** (`portefolio_project`) mais dans un
> autre dépôt auquel cette session n'a pas accès. Cette note est donc **portable** : elle décrit la
> donnée et deux voies d'intégration, calquées sur les conventions déjà en place dans le portfolio
> (ingestion WFS/HTTP → GeoParquet EPSG:2154, cf. `scrutech/mini_dc/outil/telecharge_ebc.py` et
> `telecharge_arcep.py`, puis sortie carto PMTiles/WebGIS). Une fois le dépôt de l'outil map nommé
> (ou ajouté à la session), la section « Intégration » peut être précisée à sa stack exacte.

---

## 1. Ce qu'est la donnée

**« Carte des zones en contrainte pour raccorder de nouveaux projets de production HTA/BT »** —
service co-produit **Enedis + RTE**. Il matérialise, vu du réseau de distribution, les mailles où le
raccordement d'une **nouvelle production ENR** (photovoltaïque, éolien…) est **contraint ou bloqué**
à court terme faute de capacité d'accueil disponible.

- **Nature géométrique :** couche **surfacique** (zones/mailles), pas des points.
- **Sémantique (codes couleur du visualiseur) :**
  - **rouge** — zone saturée, raccordement bloqué à court terme ;
  - **zone non saturée** — étude au cas par cas nécessaire ;
  - **blanc** — Enedis n'est pas gestionnaire du réseau (hors périmètre).
- **Attribut central attendu :** un **statut/niveau de contrainte** par zone (saturé / à étudier),
  potentiellement une capacité résiduelle et un rattachement au **poste source / S3REnR**.
- **Différence avec ce que le portfolio consomme déjà :** `mini_dc` référence déjà *Enedis Open Data —
  capacités d'accueil* comme source **ponctuelle** (`capacite_dispo_kva` par poste, cf.
  `DONNEES_REELLES.md`). La donnée étudiée ici est **complémentaire et distincte** : un **zonage
  réglementaire/opérationnel de saturation**, plus proche d'un masque d'exclusion que d'un score.

## 2. Accès à la donnée — trois hypothèses (à confirmer)

Le portail Enedis Open Data tourne sur **Opendatasoft** (`data.enedis.fr` / `enedis.opendatasoft.com`),
qui expose des API standard. Le CRS natif des jeux réseau Enedis est **RGF93 / Lambert-93 (EPSG:2154)**.
Selon que les **polygones** de contrainte sont publiés en open data ou seulement affichés dans le
visualiseur, trois voies sont possibles :

| # | Voie | Mécanisme | Idéal pour |
|---|------|-----------|-----------|
| **A** | **Jeu open data Opendatasoft** | `GET /api/explore/v2.1/catalog/datasets/{id}/exports/geojson` (ou `parquet`), API records, WFS/WMS Opendatasoft | Ingestion propre → GeoParquet, rejeu offline |
| **B** | **Flux carto WMS/WFS Enedis** | Service OGC de `openservices.enedis.fr` (« cartographie des réseaux ») | Superposition **live** dans un viewer web/QGIS |
| **C** | **Sources voisines** | **Caparéseau** (RTE, `capareseau.fr` — capacités S3REnR) ou `data.gouv.fr` (org. Enedis) | Fallback si le zonage n'est pas ouvert |

> 🔎 **Point à vérifier en premier (bloquant).** Le lien fourni est d'abord un **visualiseur**. Il faut
> confirmer qu'il existe une **couche téléchargeable** (dataset Opendatasoft ou endpoint WFS) des
> polygones de contrainte, et non un simple fond de carte propriétaire. Les pages Enedis renvoient
> **HTTP 403** à un fetch automatisé ; la vérification se fait à la main dans un navigateur sur
> <https://data.enedis.fr/datasets> (chercher « contrainte » / « capacité d'accueil » / « S3REnR »),
> ou via l'onglet **API** du dataset une fois trouvé. **Tant que ce point n'est pas tranché, la voie B
> (affichage WMS) est le plan de repli garanti** ; la voie A n'est possible que si un dataset existe.

## 3. Deux modes d'intégration dans l'outil map

### Mode 1 — Superposition live (voie B) — *le moins cher*
Ajouter la couche Enedis comme **overlay WMS** par-dessus le fond existant. Aucune donnée stockée, toujours
à jour, mais dépendance réseau à l'exécution et pas d'analyse spatiale locale.

- **Viewer web (Leaflet)** : `L.tileLayer.wms(url, { layers, format:'image/png', transparent:true })`
- **MapLibre GL** : source `raster` pointant le `GetMap` WMS.
- **QGIS** : ajout d'une couche WMS/WFS (utile pour un contrôle visuel rapide).

### Mode 2 — Ingestion → couche versionnée (voie A) — *aligné sur le portfolio*
Reproduire le patron `telecharge_*.py` : télécharger, reprojeter en **EPSG:2154**, écrire un
**GeoParquet** propre, puis publier en **PMTiles/GeoJSON** pour le WebGIS (comme `mini_dc`/`paff`).
Permet le **rejeu offline**, les **tests**, et surtout de **croiser** la contrainte ENR avec les autres
couches (parcelles, capacités poste, exclusions) comme un **filtre d'exclusion supplémentaire**.

Squelette (à adapter à l'`{id}` réel une fois confirmé) :

```python
# telecharge_enedis_contrainte_enr.py — patron identique à telecharge_ebc.py
import urllib.request, urllib.parse, json
import geopandas as gpd

# Opendatasoft export GeoJSON (à confirmer : id du dataset + host data.enedis.fr)
BASE = "https://data.enedis.fr/api/explore/v2.1/catalog/datasets"
DATASET = "<id-a-confirmer>"                      # ex. zones-en-contrainte-...
URL = f"{BASE}/{DATASET}/exports/geojson"
UA = {"User-Agent": "portfolio-sig/1.0 (etude)"}

def telecharger(out_path, bbox_2154=None):
    req = urllib.request.Request(URL, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        fc = json.loads(r.read().decode("utf-8"))
    gdf = gpd.GeoDataFrame.from_features(fc["features"], crs=4326).to_crs(2154)
    # contrat minimal : identifiant + statut de contrainte + géométrie
    # gdf = gdf[["id", "statut_contrainte", "geometry"]]
    if bbox_2154:                                  # clip optionnel sur l'AOI
        gdf = gdf.cx[bbox_2154[0]:bbox_2154[2], bbox_2154[1]:bbox_2154[3]]
    gdf.to_parquet(out_path, index=False)
    return gdf
```

> Si la voie A n'aboutit pas (pas de dataset ouvert), le même script cible l'**endpoint WFS** en
> `OUTPUTFORMAT=application/json` avec `BBOX` — exactement le code déjà écrit dans `telecharge_ebc.py`.

## 4. Licence, attribution, fraîcheur

- **Licence :** les jeux Enedis Open Data sont publiés sous **Licence Ouverte / Etalab 2.0** →
  réutilisation libre, y compris commerciale, avec **attribution « Enedis »** (et **RTE** ici, vu la
  co-production). **À reconfirmer sur la fiche du dataset**, car un visualiseur peut porter des CGU plus
  restrictives que l'open data sous-jacent.
- **Mention à afficher :** *« Zones de contrainte ENR — Enedis / RTE, Licence Ouverte Etalab 2.0 »*.
- **Fraîcheur :** donnée **évolutive** (saturation qui bouge avec les files d'attente de raccordement
  et les S3REnR). En mode 2, prévoir un **rafraîchissement périodique** (cron/GitHub Actions, comme
  `portfolio.yml`) plutôt qu'un import figé ; en mode 1, la fraîcheur est automatique.

## 5. Effort, risques, recommandation

| | Mode 1 (WMS live) | Mode 2 (ingestion GeoParquet) |
|---|---|---|
| **Effort** | Faible (½–1 j) | Moyen (2–3 j : script + tests + PMTiles + refresh) |
| **Dépendance réseau à l'usage** | Oui | Non (offline après import) |
| **Croisement analytique** | Non | Oui (filtre d'exclusion, jointures) |
| **Fraîcheur** | Auto | À planifier |
| **Pré-requis** | Endpoint WMS ouvert | **Dataset/WFS ouvert (à confirmer)** |

**Risques principaux**
1. **Disponibilité open data incertaine** — le zonage n'est peut-être qu'un fond propriétaire du
   visualiseur (⇒ mode 1 seulement, voire recours à **Caparéseau**). *À lever en premier.*
2. **Sémantique des attributs** — statut de contrainte à cartographier précisément avant d'en faire un
   filtre d'exclusion.
3. **Échelle** — zonage à la **maille poste/S3REnR**, cohérence à vérifier avec la granularité fine
   (parcelle, poste BT) de l'outil map.
4. **CGU** — bien distinguer licence du **jeu open data** vs conditions du **service cartographique**.

**Recommandation.** **Faisable et pertinent.** Démarrer par une **vérification manuelle** de l'existence
d'un dataset/WFS ouvert (§2). Puis :
- si **oui** → **mode 2**, un `telecharge_enedis_contrainte_enr.py` calqué sur `telecharge_ebc.py`,
  sortie GeoParquet EPSG:2154 + tuile PMTiles, intégré à l'outil map comme **couche d'exclusion ENR** ;
- si **non** → **mode 1** (overlay WMS) en attendant, avec **Caparéseau** comme source de repli pour la
  capacité d'accueil.

## 6. Prochaines étapes concrètes

1. **Confirmer l'endpoint** (dataset Opendatasoft `data.enedis.fr` ou WFS `openservices`) et **noter
   l'`{id}` + le format**.
2. **Nommer/ajouter le dépôt de l'outil map** à la session → adapter la section §3 à sa stack réelle
   (Leaflet / MapLibre / QGIS / pipeline PMTiles).
3. **Prototyper** le mode retenu sur **une AOI** (ex. un département) et **valider** la sémantique du
   statut de contrainte.
4. **Câbler** la couche (overlay ou filtre) + **attribution** Enedis/RTE + **refresh** périodique.

---

### Sources
- [Enedis — Carte des zones de contrainte projets ENR (service)](https://openservices.enedis.fr/service/carte-zones-contrainte-projets-enr/)
- [Observatoire de la transition écologique — fiche du service](https://observatoire.enedis.fr/services/carte-zones-contrainte-projets-enr)
- [Enedis Open Data — catalogue de données (Opendatasoft)](https://data.enedis.fr/datasets)
- [Enedis Open Data — cartographie des réseaux](https://opendata.enedis.fr/pages/cartographie)
- [Caparéseau — capacités d'accueil du réseau (RTE)](https://www.capareseau.fr/)
- [data.gouv.fr — organisation Enedis (ERDF)](https://www.data.gouv.fr/organizations/electricite-reseau-distribution-france/datasets)
