# Architecture de données & pipelines spatiaux — 3 sujets stratégiques

> Rôle : Lead Geodata Engineer / Architecte SIG.
> Stack imposée : ingestion API/IoT → Data Lake S3 → backend Python (GeoPandas,
> Rasterio, NetworkX, Boto3, FastAPI…) → WebGIS public interactif.

**Décision d'architecte transverse :** les trois projets partagent ~80 % du backbone.
Il est factorisé en [§4](#4--le-backbone-commun-à-construire-une-fois) plutôt que
répété trois fois. Ne pas reconstruire trois stacks.

---

## Sujet 1 — PAFF (Protection Automatisée Feux de Forêt)

Seul sujet en **temps réel dur**. Point de vigilance n°1 : **S3 n'est pas un magasin
temps réel**. Le pattern de prod est un *dual path* — chemin chaud (bus mémoire,
latence < 1 s) découplé du data lake froid S3 (rejeu, entraînement, archivage légal).
Faire transiter un capteur thermique par S3 pour décider en T+15 min serait une faute
d'architecture.

### Sources / APIs
| Donnée | Source | Accès |
|---|---|---|
| Vent / T° / humidité (driver n°1) | Météo-France AROME 1.3 km, ou Open-Meteo (u/v wind) | REST batch 15 min |
| Points chauds satellite (backup/validation) | NASA FIRMS (VIIRS 375 m, MODIS) | API near-real-time |
| Capteurs sol thermiques | Réseau LoRaWAN / MQTT | Flux IoT push |
| Drone IR | Push RTSP / orthomosaïque thermique | Flux |
| Topographie | RGE ALTI 1 m (IGN) ou Copernicus DEM GLO-30 | COG statique |
| Combustible / biomasse sèche | **Couche télédétection VégéVigie déjà qualifiée** | COG statique |

### Stockage S3
- **Rasters statiques** (DEM, pente, exposition, combustible) → **COG**, tous
  ré-échantillonnés sur une **grille commune, même CRS (Lambert-93 / EPSG:2154), même
  origine de pixel**. Non négociable : l'automate cellulaire lit ces couches comme des
  `np.ndarray` alignés, sans reprojection à la volée dans la boucle.
- **Télémétrie capteurs** (chemin froid) → GeoParquet partitionné
  `raw/telemetry/dt=YYYY-MM-DD/zone=<grid_id>/`.
- **Périmètres prédits T+15** → FlatGeobuf/GeoJSON léger, poussés au front par
  WebSocket (pas via S3).

### Python — libs & algo
- **NetworkX est le mauvais outil ici** : la propagation de feu est un problème de
  **grille**, pas de graphe.
- **Automate cellulaire sur raster** (modèle de Rothermel pour la vitesse, correction
  pente + vent de Van Wagner). Pas de lib pip clé-en-main solide (ELMFIRE/FARSITE hors
  Python) → **noyau implémenté en NumPy vectorisé + `numba`** (`@njit`). ~200 lignes,
  pas un framework.
- Champ de vent interpolé depuis les capteurs → IDW (commencer simple) ou krigeage
  (`pykrige`) si densité suffisante.
- `rasterio` (I/O COG windowed), `scikit-image` (morphologie du front), `xarray`.
- **Déclenchement** : périmètre prédit (polygone `shapely`) ∩ zones d'actifs.
- Orchestration chemin chaud : **FastAPI async + `paho-mqtt`** + **Redis** (état du
  front). Pas de Kafka tant qu'un seul massif — Kafka = phase multi-régions.

### Restitution Web
**Deck.gl** — seul cas où l'animation GPU temps réel est indispensable. `TripsLayer` /
`PolygonLayer` animé pour le front, `H3HexagonLayer` pour l'aléa, fond **MapLibre**
(pas Mapbox, licence). Push live par **WebSocket**. Leaflet exclu (perf insuffisante).

---

## Sujet 2 — Carrefours de biodiversité / stepping stone parfait

Ici **NetworkX est parfaitement à sa place** — cas d'usage canonique des graphes spatiaux.

### Sources / APIs
| Donnée | Source |
|---|---|
| Trame Verte & Bleue / réservoirs | SRCE régionaux, OFB, Géoportail |
| Occupation du sol (surface de résistance) | CES OSO (Theia) ou Corine Land Cover |
| Barrières | OpenStreetMap (routes, voies ferrées) via Overpass / `osmnx` |
| Trame Noire (pollution lumineuse) | VIIRS DNB (NOAA night lights) |
| Foncier candidat + coût compensation | Cadastre PCI + DVF (prix → coût réel du « pont ») |
| Zonages | Natura 2000, ZNIEFF (INPN) |

### Stockage S3
- Surface de résistance (raster pondéré occupation × barrières × luminosité) → **COG**.
- Réservoirs + parcelles candidates → **GeoParquet** partitionné région/département.
- Graphe (nœuds/arêtes) → Parquet (deux tables), GraphML seulement pour debug.
  Partition H3 res 8–9 cohérente avec le reste du portfolio.

### Python — libs & algo
1. Fusionner les 3 trames en **une surface de résistance unique** (raster). La Trame
   Noire y entre comme facteur multiplicatif de résistance nocturne.
2. **Chemins de moindre coût** entre réservoirs : `skimage.graph.MCP_Geometric` /
   `route_through_array`.
3. Construire le graphe : réservoirs = nœuds, arêtes pondérées par la distance de
   moindre coût effective. `networkx`.
4. **Sélection « haute couture » = métrique dPC (delta Probability of Connectivity,
   méthode Conefor)** : pour chaque parcelle candidate, l'ajouter comme nœud-relais,
   recalculer PC, **classer par ΔPC**. La parcelle au ΔPC maximal *est* le stepping
   stone parfait. Plus fin que la simple betweenness centrality
   (`nx.edge_betweenness_centrality`, à garder comme baseline).
5. `networkx`, `scikit-image`, `rasterio`, `geopandas`, `scipy.sparse` si le graphe
   grossit. `graph-tool` seulement si NetworkX rame (>10⁵ nœuds) — sinon YAGNI.

### Restitution Web
Analytique, pas temps réel → **deck.gl en overlay sur MapLibre** : `ArcLayer`/
`LineLayer` pour les corridors, `GeoJsonLayer` pour réservoirs + parcelle élue. Surface
de résistance en fond → **PMTiles**. `kepler.gl` pour prototyper sans code.

---

## Sujet 3 — Trame Blanche (corridors de silence)

Le plus lourd en calcul physique. **Il n'existe pas de lib Python propre de propagation
acoustique.** La référence métier (**CNOSSOS-EU**, directive 2002/49/CE) est
implémentée dans **NoiseModelling** (Java/H2GIS). Deux choix honnêtes :
- **Pragmatique/prod** : appeler NoiseModelling en batch (job Java conteneurisé),
  Python pour l'orchestration + post-traitement. Résultat validé réglementairement.
- **Full-Python** : ré-implémenter un **ISO 9613-2 simplifié** (divergence géométrique
  + absorption atmosphérique + effet de sol + **diffraction par le relief via
  viewshed** sur le DEM). Faisable en NumPy/`numba`, mais vrai chantier.

### Sources / APIs
| Donnée | Source |
|---|---|
| Sources terrestres | BD TOPO (routes/rail + trafic), ICPE (industrie) |
| Sources maritimes | AIS (trajectoires navires) via aishub / Spire |
| Relief terrestre | RGE ALTI / Copernicus DEM (COG) |
| Bathymétrie (marin) | EMODnet Bathymetry, GEBCO |
| Cartes de bruit existantes | CNOSSOS stratégiques, Bruitparif |

### Stockage S3
- DEM / bathymétrie → **COG**. Surface de bruit calculée (grille dB) → **COG**.
- Sources → **GeoParquet** (points/lignes avec niveau d'émission dB).
- AIS maritime → GeoParquet partitionné par jour (données temporelles massives).

### Python — libs & algo
- Propagation : voir choix ci-dessus. Diffraction relief = profils de visibilité
  ligne-de-vue → `richdem` / GDAL viewshed, ou profils extraits avec `skimage`.
- **Corridors de silence** : **inverser la grille dB en surface de résistance
  « quiétude »**, puis réutiliser *exactement* le même moteur que le Sujet 2
  (`skimage.graph` moindre coût + `networkx`). Point de mutualisation clé : Sujets 2 et
  3 partagent l'algo de corridors, seule la surface de résistance change.
- AIS → trajectoires : **`movingpandas`** + `pandas` → densité de source dynamique.
- `rasterio`, `numpy`, `numba`, `scipy.ndimage`, `xarray`.

### Restitution Web
Seul cas où la **3D apporte vraiment** : **deck.gl `TerrainLayer`** (relief/bathymétrie)
avec la nappe de bruit drapée en texture — on *voit* le son buter sur la topographie.
Fond MapLibre 3D terrain. Time-slider deck.gl pour la dynamique maritime AIS. Service
raster via **titiler** (tuilage dynamique du COG dB).

---

## 4 — Le backbone commun (à construire UNE fois)

Les 3 projets ne sont pas 3 stacks, c'est **1 plateforme × 3 domaines** :

| Couche | Choix unique | Justification |
|---|---|---|
| **Lake S3** | `raw/ → staged/ → curated/`, tout raster en **COG grille+CRS communs (L93)**, tout vecteur en **GeoParquet partitionné H3/admin** | zéro reprojection à la volée, requêtes cloud-native |
| **Découverte** | Catalogue **STAC** (déjà en place avec VégéVigie) | même mécanisme d'ingestion pour les 3 |
| **Moteur requête** | **DuckDB-spatial + httpfs** | scan ciblé sur S3, pas de download massif |
| **Cœur commun** | *Surface de résistance → `skimage.graph` moindre coût → `networkx`* | **Sujets 2 et 3 partagent ce moteur** ; l'écrire une fois |
| **Service** | **FastAPI** + **titiler** (tuiles COG) | une API pour les 3 |
| **Front** | **MapLibre + deck.gl**, exports **PMTiles** | un seul socle, layers spécialisés par sujet |
| **Orchestration** | Batch simple (`prefect` léger / cron). **Seul le PAFF sort** vers un chemin chaud MQTT/Redis | pas de Kafka/Dagster « au cas où » |

**Dette évitée dès maintenant** : Kafka généralisé (seul le PAFF le justifie, en
multi-régions), `graph-tool` avant d'avoir mesuré NetworkX, réimplémenter CNOSSOS en
Python si NoiseModelling suffit.

---

## Question ouverte (conditionne l'archi du PAFF)

La boucle de décision T+15 doit-elle être **pleinement autonome** (déclenchement canon
sans humain) ou **human-in-the-loop** (le système propose, un opérateur valide) ? Cela
change radicalement les exigences de latence, de logging légal sur S3, et de tolérance
aux faux positifs — donc l'archi du chemin chaud.
