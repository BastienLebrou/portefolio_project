# Brancher des données réelles (sources publiques)

L'outil tourne par défaut sur des données **synthétiques** (Alba-la-Romaine).
Pour le tester sur du réel, télécharge les sources publiques ci-dessous, dépose
les fichiers dans `data/sources_reelles/`, puis lance :

```bash
python adapter_donnees_reelles.py     # convertit -> data/raw/*.parquet
python run.py --no-generate           # exécute le pipeline sur le réel
```

L'adapter est **tolérant** : il devine les colonnes (plusieurs noms candidats),
clippe sur l'AOI si fournie, et ignore proprement toute source absente.

## Scripts de téléchargement prêts à l'emploi

Deux sources sont déjà automatisées (sortie directe en GeoParquet EPSG:2154
dans `Data_alba/`) :

```bash
python telecharge_arcep.py     # fibre ARCEP -> Data_alba/fibre.parquet
python telecharge_ebc.py       # EBC (GPU)   -> Data_alba/ebc.parquet
```

- **`telecharge_arcep.py`** : « Ma connexion internet » (data.arcep.fr). Joint la
  base immeuble (`base_imb_{dept}`) et l'éligibilité (`actuel_{dept}`) pour donner,
  par immeuble, le **statut fibre** (`Déployé` si techno `FO` présente) + le type
  (PA pavillon / IM immeuble). Options `--dept` / `--insee`.
- **`telecharge_ebc.py`** : Espaces Boisés Classés via le WFS du Géoportail de
  l'Urbanisme (`wfs_du:prescription_surf`, `typepsc='01'`), découpés sur la commune.

> Les fichiers téléchargés dans `Data_alba/` ne sont **pas** versionnés (gitignore).

## AOI (recommandé en premier)

Dépose un contour de commune nommé `commune*.geojson` (ou `aoi*.geojson`) pour
restreindre tous les calculs à la zone d'étude. Source : contours IGN Admin
Express, ou cadastre Etalab (couche communes).

## Sources par couche

| Couche (fichier attendu) | Source publique | Format | Colonnes clés repérées |
|---|---|---|---|
| `*parcelle*` | **Cadastre Etalab / PCI vecteur** — cadastre.data.gouv.fr | GeoJSON/GPKG | `idu`, `commune`, géométrie |
| `*bati*` | **BD TOPO IGN** (bâti) ou cadastre Etalab (bâtiments) | GPKG/SHP | `usage_1`, `nature` |
| `*arcep*` / `*fibre*` | **ARCEP** — data.arcep.fr (IPE / Ma connexion internet) | CSV/GeoJSON | `statut_deploiement`, lon/lat |
| `*enedis*` / `*poste*source*` | **Enedis Open Data** — opendata.enedis.fr (capacités d'accueil) | CSV/GeoJSON | `capacite_dispo_kva`, lon/lat |
| `*irve*` / `*borne*` | **IRVE** — transport.data.gouv.fr | CSV/GeoJSON | lon/lat |
| `*photovolt*` / `*pv*` | **Registre ODRÉ / Enedis-RTE** | CSV/GeoJSON | lon/lat |
| `*monument*` / `*mh*` | **Atlas des patrimoines / Mérimée / GPU** | GeoJSON | `nom`, géométrie |
| `*ppri*` / `*inondation*` | **Géorisques** (zonage réglementaire PPR) | GeoJSON | `niveau_risque` |
| `*ebc*` / `*boise*` | **Géoportail de l'Urbanisme** (prescriptions surfaciques) | GeoJSON/GPKG | géométrie |
| `*route*` / `*voie*` | **BD TOPO** (tronçon de route) ou **OSM** | GeoJSON/GPKG | géométrie |

## Notes geo-data engineer

- **CRS** : tout est reprojeté en **EPSG:2154** automatiquement. Si un fichier
  n'a pas de CRS défini, l'adapter suppose WGS84 (à vérifier).
- **Volumétrie France** : pour passer à l'échelle, télécharge par **département**
  et garde le partitionnement `dept` (déjà géré). Le pipeline H3 ne changera pas.
- **Colonnes manquantes** : si une source n'a pas la colonne attendue (ex. pas de
  capacité kVA Enedis), l'adapter met une valeur neutre — le filtre correspondant
  sera alors peu discriminant. Adapte les noms dans `adapter_donnees_reelles.py`
  si ton export utilise des intitulés exotiques.
- **Aucune donnée n'est versionnée** : `data/` est dans le `.gitignore`.
