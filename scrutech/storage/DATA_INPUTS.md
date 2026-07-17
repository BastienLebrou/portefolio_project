# Données d'entrée par fonction — cible AOI-first

**Principe.** Tu fournis **UNE emprise (AOI)** — un code INSEE, un département, une bbox
ou une couche. Chaque fonction dérive tout le reste **automatiquement** : soit par
**appel API à la volée** (🌐), soit depuis un **cache local GeoParquet/COG + BDD DuckDB**
(💾, → S3 plus tard). Certaines données sont **calculées par un autre pilier** (🧮).

Objectif : QGIS devient **optionnel** (simple lecteur des couches précalculées) ; les
traitements tournent côté backend.

Légende : 🌐 API à la volée · 💾 cache local/BDD (→ S3) · 🧮 dérivé d'un autre pilier

---

## 1. VegeVigie — tendance & sécheresse
**Entrée idéale : `AOI`** (+ `années`, `résolution` par défaut).

| Donnée SIG | Source | Mode |
|---|---|---|
| Sentinel-2 L2A (Red, NIR, SCL) | STAC Microsoft Planetary Computer | 🌐 streaming COG (jamais stocké brut) |
| Communes (agrégation zonale) | `geo.api.gouv.fr` | 🌐 |

**Persisté** : COG `trend`/`drought` + table `vege_commune_stats` (BDD). QGIS lit ça.

---

## 2. PAF — interface habitat-forêt (WUI)
**Entrée idéale : `AOI`** (+ `contact_m` = 50). **Aucune couche à sélectionner.**

| Donnée SIG | Source | Mode |
|---|---|---|
| **Zones construites** | **OCS GE** (IGN) — couverture *surfaces artificialisées / bâti* | 💾 |
| Forêt | **OCS GE** — couverture *zones arborées* (ou couche vulnérable VegeVigie) | 💾 / 🧮 |

> Les deux couches PAF sortent du **même produit OCS GE** (une requête, deux classes de
> couverture) → AOI seule, plus rien à sélectionner.

---

## 3. Écobuage — aptitude au brûlage
**Entrée idéale : `AOI`** (+ `poids` par défaut). **Plus de rasters à fournir.**

| Critère | Source | Mode |
|---|---|---|
| Combustible / biomasse sèche | NDVI/NBR VegeVigie | 🧮 |
| Embroussaillement | tendance NDVI VegeVigie | 🧮 |
| Pente | RGE ALTI (IGN) ou Copernicus DEM GLO-30 | 💾 COG |
| Accessibilité | voirie BD TOPO ou routes OSM (Overpass) | 🌐 / 💾 |
| Historique feux | BDIFF + EFFIS (périmètres brûlés) | 💾 |
| Exclusions | Natura 2000 (INPN), zones construites (**OCS GE**), occupation du sol (**OCS GE**) | 💾 |

---

## 4. SDBPi — bâtiments professionnels inoccupés
**Entrée idéale : `AOI`** (INSEE ou emprise) (+ `buffer` = 25 m).

| Donnée SIG | Source | Mode |
|---|---|---|
| Bâti (commercial/industriel) | BD TOPO `BDTOPO_V3:batiment` (WFS) | 💾 |
| Établissements SIRENE actifs géolocalisés | `recherche-entreprises.api.gouv.fr` (ou masse Grand Lyon / fichier dép.) | 🌐 |
| Communes | `geo.api.gouv.fr` | 🌐 |

---

## 5. Mini data centers — sélection de sites
**Entrée idéale : `AOI`** (commune ou emprise). **Fin de la commune codée en dur / démo synthétique.**

| Donnée SIG | Source | Mode |
|---|---|---|
| Parcelles cadastrales | `cadastre.data.gouv.fr` (PCI Vecteur) | 🌐 / 💾 |
| **Zones construites** (contexte bâti) | **OCS GE** (IGN) | 💾 |
| Fibre | ARCEP (open data déploiement fibre) | 💾 |
| Énergie | Enedis (postes sources / capacités d'accueil réseau) | 💾 |
| Voirie | BD TOPO `troncon_de_route` / OpenStreetMap | 💾 / 🌐 |
| Contraintes | ABF/monuments, PPRI (`Géorisques` API), EBC (`GPU` — Géoportail Urbanisme) | 🌐 / 💾 |

---

## 6. Load communes (helper)
Sera **absorbé par `resolve_aoi`** : dès qu'une AOI = INSEE/dept, les communes sont
récupérées automatiquement (`geo.api.gouv.fr`). Fonction dédiée à retirer à terme.

---

## Règle : API à la volée vs stockage

- **🌐 À la volée** (léger, interrogeable, volatil) : SIRENE, communes, cadastre (petite
  AOI), Overpass (routes), PPRI (Géorisques), GPU (urbanisme).
- **💾 Cache GeoParquet/COG + DuckDB** (lourd, réutilisé) : BD TOPO (bâti/forêt/voirie),
  DEM, ARCEP, Enedis, BDIFF, Natura 2000, occupation du sol. Local d'abord, **S3** ensuite.
- **Sentinel-2** : streaming COG (jamais stocké brut) ; seuls les **dérivés** persistent.

## Contrat de lecture (front-ends)

Une couche affichée = `SELECT … FROM <table> WHERE aoi_id = ?` **ou** un chemin
`storage.product_path(pilier, aoi_id, produit)`. Aucun calcul lourd côté QGIS ; les algos
**natifs** (PAF WUI, écobuage scoring) restent exécutables in-process car sans stack lourde.

## Ce que ça change vs aujourd'hui

| Fonction | Aujourd'hui (à corriger) | Cible |
|---|---|---|
| VegeVigie | exige un `PYTHON_EXE` avec la stack | AOI → backend calcule → QGIS lit |
| PAF | exige couches forêt + bâti | **AOI seule** ; bâti + forêt auto |
| Écobuage | exige 5 rasters alignés | **AOI seule** ; critères dérivés auto |
| SDBPi | INSEE + venv externe | **AOI** ; données à la volée / BDD |
| Mini DC | démo Alba, pas d'AOI | **AOI** réelle |

---

## Sources — accès détaillé

> ⚠️ Endpoints **best-known (2026), non vérifiés sur le web** (recherche plafonnée) —
> à confirmer au premier run d'ingestion. `geoservices.ign.fr` redirige désormais vers
> `cartes.gouv.fr` (confirmé).

| Donnée | Fournisseur | Accès |
|---|---|---|
| **OCS GE** (zones construites + forêt) | IGN | `cartes.gouv.fr` / `data.geopf.fr` — téléchargement GPKG par département, ou WFS. Couverture bâti = surfaces artificialisées (CS1.1.x). |
| **Historique feux — BDIFF** | Min. Agriculture | `bdiff.agriculture.gouv.fr` — export CSV (date, INSEE commune, surface parcourue), national, filtrable par département. |
| **Historique feux — EFFIS** | Copernicus / JRC | `effis.jrc.ec.europa.eu` — périmètres de zones brûlées (shapefile/GeoJSON), filtrable France. |
| **Fibre — ARCEP** | ARCEP | `data.gouv.fr` (jeux ARCEP « déploiement FTTH » / « Ma connexion internet »), par région/département. |
| **Énergie — Enedis** | Enedis | `opendata.enedis.fr` — API Opendatasoft : `…/api/explore/v2.1/catalog/datasets/{dataset}/exports/geojson`. Jeux : postes sources, capacités d'accueil réseau, réseau HTA/BT. |
| **Voirie** | IGN / OSM | BD TOPO `BDTOPO_V3:troncon_de_route` (WFS `data.geopf.fr`, ou GPKG par département) ; ou OSM via Overpass `overpass-api.de/api/interpreter`. |
| **Natura 2000** | INPN | `inpn.mnhn.fr` / `data.gouv.fr` — shapefiles nationaux SIC/ZSC + ZPS, à clipper sur l'emprise. |
| **Communes / départements** | Etalab | `geo.api.gouv.fr` (vérifié). |
