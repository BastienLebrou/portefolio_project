# Interface habitat-forêt (WUI) — module `interface`

Premier module implémenté du PAFF. Il calcule la **frontière forêt↔bâti**, la
géométrie la plus critique du feu : débroussaillement légal, chaleur radiante et sautes
de braises agissent tous dans une bande étroite de part et d'autre de cette ligne.

Voir le schéma d'implantation : [`schema_paff_interface.svg`](schema_paff_interface.svg).

## Ce que ça calcule

À partir de deux couches d'entrée (zones forêt classées VégéVigie + zones bâti), dans
une emprise :

- **`interface_line`** — les segments de lisière forêt à moins de `contact_m` d'un
  bâtiment : la frontière elle-même ;
- **`interface_zone`** — la bande de forêt dans les `contact_m` du bâti = l'emprise OLD
  (Obligation Légale de Débroussaillement) **et** la zone prioritaire à défendre côté
  PAFF ;
- **métriques** — longueur de frontière (km), surface de bande à traiter (ha), bâti
  exposé (ha).

Toutes les mesures de distance/surface se font en CRS projeté (Lambert-93 par défaut) ;
les entrées dans n'importe quel CRS sont reprojetées d'abord.

## Algorithme (cœur pur, testable offline)

```python
forest_u = forest.to_crs(metric_crs).union_all()   # clip à l'emprise en amont
bati_u   = bati.to_crs(metric_crs).union_all()
reach    = bati_u.buffer(contact_m)                 # 50 m = OLD par défaut
line     = forest_u.boundary.intersection(reach)    # la frontière
zone     = forest_u.intersection(reach)             # la bande à traiter
```

## Sorties

Dans `data/processed/` :

| Fichier | CRS | Usage |
|---|---|---|
| `interface_line.parquet`, `interface_zone.parquet` | métrique (L93) | QGIS / GeoPandas |
| `interface_line.geojson`, `interface_zone.geojson` | WGS84 | front deck.gl / MapLibre |

## Usage CLI

```bash
vegevigie interface  forets_vegevigie.gpkg  bati.gpkg \
  --aoi emprise.parquet  --contact-m 50 \
  --config <...>/qgis_plugin/scrutech/config/default.yaml
```

- **Emprise** : `--aoi <couche>` (tout format/CRS) **ou** `--bbox "minx,miny,maxx,maxy"`
  (interprété dans le CRS métrique = cas « étendue du canevas QGIS »). Sans emprise :
  toute l'étendue des couches.
- **Formats d'entrée** : parquet, gpkg, shp, geojson.
- **Paramètres** (`config/default.yaml`, section `interface:`) : `contact_m` (50 m,
  OLD), `metric_crs` (EPSG:2154). `--contact-m` surcharge ponctuellement.

## Vérification (venv projet, GeoPandas 1.1.4)

Testé sur données synthétiques (un bloc forêt + bâtiments à distances variées) :

- Frontière calculée (196 m), types `MultiLineString` / `MultiPolygon` — OK
- Clip sur emprise → frontière rognée (196 → 106 m) — OK
- Exports GeoJSON WGS84 écrits — OK
- Cas « aucun contact » (bâti éloigné) → géométries vides, métriques à zéro, pas de
  crash — OK
- CLI de bout en bout : `exit_code 0`, config validée, `--help` propre — OK

## Points connus

1. **Bug pré-existant dans la copie scrutech (non introduit par ce travail)** :
   `config.py::DEFAULT_CONFIG_PATH` utilise `parents[2]`, qui pointe vers
   `qgis_plugin/config/` au lieu de `qgis_plugin/scrutech/config/`. Artefact de recopie
   depuis `src/` (où `parents[2]` est correct). Touche **toutes** les commandes de la
   copie → il faut passer `--config` explicitement, ou corriger en `parents[1]`.
2. **`src/` et `tests/` non modifiés** : le double `src/vegevigie/` et les tests pytest
   n'ont pas été touchés. Miroir + `tests/test_interface.py` = suivi d'une étape.

## Suite logique côté PAFF

Segmenter `interface_line` en **tronçons priorisés** (longueur × vulnérabilité VégéVigie
× proximité bâti) pour donner au moteur temps réel des cibles ordonnées.
