# SDBPi — Système de Détection des Bâtiments Professionnels Inoccupés

Croisement **open data BD TOPO (bâti) × SIRENE (activité)** sur une emprise (commune
ou bbox). Méthode type *Cerema* : un bâtiment à usage **commercial/industriel** ne
contenant (ni à proximité immédiate) **aucun établissement SIRENE actif géolocalisé**
est un **CANDIDAT à l'inoccupation**.

> ⚠️ **Le résultat liste des CANDIDATS, pas des certitudes.** Un SIRET peut être une
> simple domiciliation (siège « boîte aux lettres ») sans activité réelle ; un local
> réellement vide peut conserver un SIRET résiduel ; un établissement actif mal
> géocodé (BAN) peut tomber hors du buffer. **La sortie sert à PRIORISER une
> vérification terrain**, pas à conclure.

## Arborescence

```
sdbpi/                # projet AUTONOME (open data uniquement)
├── config.py        # ZONE, BUFFER_M, USAGES_CIBLE, source SIRENE, mapping PLM, chemins (aucun hardcode)
├── net.py           # session HTTP robuste (retry/backoff/timeout), erreurs claires
├── sources.py       # acquisition + cache : commune, bâtiments WFS, SIRENE (+ expansion arrondissements)
├── processing.py    # fonctions pures GeoPandas : filtre, jointure, statut, synthèse
├── run_vacance.py   # orchestration + CLI
├── naf_rev2_subclasses.json  # 732 codes NAF figés (sous-partition anti-plafond API)
├── requirements.txt
├── cache/           # téléchargements mis en cache (créé au 1er run)
└── BDD/_vacance/{zone}/  # sorties GeoPackage + GeoParquet
```

## Installation

```powershell
pip install -r requirements.txt
```

## Utilisation

```powershell
# Commune (crash-test recommandé)
python run_vacance.py --insee 01053

# Buffer plus large (recommandé en zone industrielle, voir plus bas)
python run_vacance.py --insee 01053 --buffer 30

# Emprise bbox WGS84 (minx,miny,maxx,maxy)
python run_vacance.py --bbox 5.21,46.19,5.25,46.22

# Restreindre les usages cibles
python run_vacance.py --insee 01053 --usages "Industriel"

# Emprise polygonale depuis un fichier (.parquet/.gpkg/.geojson) en EPSG:2154
# + source SIRENE en masse "Métropole de Lyon" (idéal pour une emprise Grand Lyon)
python run_vacance.py --emprise emprise_etude.parquet --source grandlyon

# Source SIRENE = fichier départemental pré-géocodé (passage à l'échelle)
python run_vacance.py --insee 69123 --source geo_file --geo-file C:\data\sirene_geo_69.parquet

# Ignorer le cache
python run_vacance.py --insee 01053 --no-cache
```

Trois manières de définir la zone (exclusives) : `--insee`, `--bbox`, `--emprise`.
Trois sources SIRENE : `api` (défaut, par commune), `geo_file` (fichier dép. fourni),
`grandlyon` (Base Sirene Métropole de Lyon, ~338k actifs géolocalisés — voir ci-dessous).

## Sources & endpoints (vérifiés en live le 2026-06-15 — ils bougent)

| Donnée | Endpoint | Points d'attention codés |
|---|---|---|
| Bâtiments BD TOPO | `https://data.geopf.fr/wfs/ows` · WFS 2.0.0 · `BDTOPO_V3:batiment` | **COUNT plafonné à 5000/req** → pagination `STARTINDEX`. Axes BBOX en EPSG:2154 = (easting, northing). Géométries 3D → aplaties en 2D. |
| Établissements SIRENE | `https://recherche-entreprises.api.gouv.fr/search` | **`total_results` plafonné à 10000** → **partition par section NAF** (A→U, chaque < 10000). **`per_page` max = 25**. `matching_etablissements` contient des établissements fermés → filtre `etat_administratif=="A"`. lat/lon nuls exclus. |
| SIRENE Métropole de Lyon (masse) | data.gouv → `data.grandlyon` GeoServer (mode `grandlyon`) | ~338k établissements **actifs déjà géolocalisés** (`the_geom`=POINT lon/lat, `activitenaf`, `insee`) sur ~59 communes. **1 fichier (~100 Mo, caché)** au lieu de milliers d'appels API. |
| Contour commune | `https://geo.api.gouv.fr/communes/{insee}?fields=contour&format=geojson&geometry=contour` | Clip de l'emprise (point représentatif dans la commune, footprints non découpés). |

> **Pourquoi plusieurs sources SIRENE.** L'API recherche-entreprises est parfaite à
> l'échelle d'**une commune** (partition NAF → exhaustif). Mais elle **ne passe pas à
> l'échelle d'une emprise métropolitaine** : une emprise métropolitaine recoupe ~10 communes
> (~180-220k établissements) = 8 000-9 000 pages @25 + sous-partition = plusieurs heures
> et abus de l'API. Pour le Grand Lyon, la source `grandlyon` (un fichier de masse déjà
> géolocalisé) est la bonne réponse. Le fichier cquest historique est **hors-ligne (404)** ;
> l'officiel INSEE est **national + géoloc-seule** ; le mode `geo_file` reste dispo pour
> un fichier départemental fourni.

## Méthode (pipeline)

1. Emprise → contour commune (geo.api) **ou** bbox, reprojetés en **EPSG:2154**.
2. Bâtiments BD TOPO via WFS (paginé), clippés à l'emprise.
3. Filtre `usage_1` **ou** `usage_2` ∈ `USAGES_CIBLE` (défaut : *Commercial et services*, *Industriel*). Inclut donc les immeubles mixtes résidentiel+commerce.
4. SIRENE actifs géolocalisés → points (4326 → 2154), lat/lon nuls exclus.
5. Jointure spatiale **tolérante** : pour chaque bâtiment, nb d'établissements actifs **dans le polygone OU dans un buffer `BUFFER_M`** (défaut 15 m — la géoloc SIRENE est à l'adresse BAN, souvent décalée du footprint).
6. `statut_occupation` = `VACANT_CANDIDAT` si `nb_etab_actifs == 0`, sinon `OCCUPE`. Surface = aire du polygone (m²).

## Colonnes de sortie

`id_bati, usage_1, usage_2, surface_bati_m2, hauteur, nb_etab_actifs, liste_siret,
statut_occupation, code_insee, commune, nature, geometry` (EPSG:2154).

## Résultats du crash-test (01053 Bourg-en-Bresse, buffer 15 m)

- 12 691 bâtiments dans la commune → **2 009 professionnels** → 8 600 établissements actifs géolocalisés.
- **747 candidats inoccupés** (taux apparent **37,2 %**).

### ⚠️ Sensibilité au buffer (résultat clé)

| Buffer | Candidats | Taux apparent | dont ≥ 200 m² |
|---:|---:|---:|---:|
| 15 m | 747 | 37,2 % | 359 |
| 25 m | 526 | 26,2 % | 233 |
| 50 m | 273 | 13,6 % | 115 |
| 100 m | 84 | 4,2 % | 40 |

Les 5 plus **grands** « candidats inoccupés » à 15 m ont en réalité un établissement actif
à **16–102 m** (adresse BAN en bordure de voie, loin du footprint sur grande parcelle).
**15 m sous-apparie les grandes emprises industrielles.** Recommandation : **25–30 m**
pour un tissu mixte urbain/industriel, et challenger systématiquement les grands
candidats.

## Cas d'étude : emprise Grand Lyon (source `grandlyon`, buffer 15 m)

Emprise polygonale de **126 km²** recoupant ~10 communes du cœur métropolitain
(Lyon, Villeurbanne, Vénissieux, Vaulx-en-Velin, Oullins-Pierre-Bénite, Rillieux,
Saint-Priest, Francheville…). SIRENE via la **Base Sirene Métropole de Lyon**
(337 737 actifs géolocalisés → **237 019 dans l'emprise**).

- 149 818 bâtiments (bbox) → 113 401 dans l'emprise → **19 572 professionnels**.
- **5 355 candidats inoccupés** (taux apparent **27,4 %**) ; 2 643 ≥ 200 m² ; ~343 ha.

### Sensibilité au buffer

| Buffer | Candidats | Taux apparent | dont ≥ 200 m² |
|---:|---:|---:|---:|
| 15 m | 5 353 | 27,4 % | 2 643 |
| 25 m | 3 538 | 18,1 % | 1 785 |
| 50 m | 1 641 | 8,4 % | 795 |
| 100 m | 533 | 2,7 % | 271 |

### Inoccupation apparente par commune (buffer 15 m)

| Commune | Bâti pro | Candidats | Taux |
|---|---:|---:|---:|
| Lyon | 11 481 | 1 916 | 16,7 % |
| Villeurbanne | 2 755 | 990 | 35,9 % |
| Vénissieux | 867 | 474 | 54,7 % |
| Vaulx-en-Velin | 1 040 | 403 | 38,8 % |
| Oullins-Pierre-Bénite | 610 | 207 | 33,9 % |
| Saint-Priest* | 193 | 138 | 71,5 % |
| Rillieux-la-Pape | 185 | 83 | 44,9 % |

\* communes partiellement couvertes / zones industrielles : taux gonflé par le
sous-appariement du buffer 15 m sur grandes parcelles (cf. sensibilité ci-dessus).
Le cœur dense de Lyon ressort logiquement le plus bas (16,7 %).

## Limites & pistes d'amélioration (v2)

- **Buffer fixe** : un buffer adaptatif (fonction de la taille/forme du bâtiment) ou
  l'**affectation au footprint le plus proche** (≤ d_max) limiterait sur- et
  sous-appariement. Mieux que le buffer plat.
- **Bruit des petites structures** : ~174/747 candidats < 50 m² (annexes, hangars,
  abris sans SIRET propre) → filtrer une **surface minimale** selon le besoin.
- **Domiciliation** : un siège domicilié gonfle l'occupation apparente ; croiser avec
  la nature de l'établissement / présence salariée affinerait.
- **Passage à l'échelle (département)** : préférer `--source geo_file` (un seul fichier
  départemental pré-géocodé) à des centaines d'appels API par commune.
- Mode `--bbox` : la résolution des communes pour l'API se fait par échantillonnage
  (grille 5×5) — fiable à l'échelle d'une commune, à valider pour de grandes emprises.
- **Couverture source `grandlyon`** : limitée aux ~59 communes de la Métropole de Lyon.
  Un débord de l'emprise hors Métropole n'est pas couvert par cette source.
- **Affectation commune** : le découpage par commune (QA) utilise le point représentatif
  du bâtiment ; quelques bâtiments en limite ou hors des 10 communes principales ne sont
  pas rattachés (≈ 2 400 / 19 572), sans effet sur le total.
