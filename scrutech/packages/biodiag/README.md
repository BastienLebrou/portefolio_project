# Biodiag

Diagnostic par analyse de données environnementales d'une emprise, à partir de la bibliographie seulement (pas
d'inventaire de terrain). On donne l'emprise du projet ; l'outil va chercher les observations
**GBIF** autour, les croise avec les **zonages INPN** (ZNIEFF, Natura 2000, APPB, réserves,
parcs) et les statuts de protection, puis rend un dossier d'écologue : enjeux par espèce, lecture
« réservoir ou dent creuse », incidences d'un parc solaire, mesures ERC, conclusion.

**La question à laquelle il répond :** que dit déjà la littérature sur ce site, et où faut-il
un inventaire ciblé ?

## Lancer

```bash
# depuis scrutech/packages/biodiag
uv sync
uv run biodiag insee:11040 --zer 1000 --zee 5000
uv run biodiag parcelles.shp --assume-crs EPSG:2154 --filter numero=1265,2784 \
    --habitat "friche ouverte à garrigue basse" --ref "PC 000 000 00 000000"
```

L'entrée est une emprise ScruTech (`insee:XXXXX`, fichier vectoriel, `minx,miny,maxx,maxy`).
Les produits vont dans `{SCRUTECH_DATA}/biodiag/aoi={aoi_id}/output/` (ou `--out`).

| Produit | Contenu |
|---|---|
| `rapport_diagnostic.pdf` / `.md` | le dossier complet |
| `carte_interactive.html` | fonds IGN/OSM/satellite, zonages, observations par enjeu |
| `occurrences_nettoyees.geojson` | observations nettoyées avec statuts et enjeu |
| `synthese_enjeux.csv` | une ligne par espèce (enjeu, protection, UICN, sensibilité solaire) |
| `zonages.geojson` | zonages de protection du rayon d'analyse |

Premier lancement sur une grande zone : le téléchargement GBIF peut prendre plusieurs minutes
(l'API limite le débit). Le résultat est mis en cache en Parquet, la relance est immédiate.

## Où est le code

| Fichier | Rôle |
|---|---|
| `src/biodiag/biodiag_aoi.py` | lance l'outil sur une emprise (et la commande `biodiag`) |
| `gbif.py` | téléchargement paginé et découpé, nettoyage, noms français |
| `taxa.py` | groupe taxonomique, protection, directives, sensibilité au solaire |
| `enjeux.py` | zones ZIP/ZER/ZEE, enjeu par observation, synthèse, contexte du paysage |
| `environment.py` | zonages INPN, cours d'eau, haies et boisements, parcs PV voisins, RPG |
| `report.py`, `pdf.py`, `maps.py` | rapport Markdown, PDF aux couleurs ScruTech, cartes |

Il s'appuie sur le socle `core` (`resolve_aoi`, `fetch_bdtopo`, `fetch_ortho`, `product_path`).

## Limites à connaître

- **Statuts indicatifs.** Protection nationale et annexes des directives viennent d'un dictionnaire
  interne (`taxa.py`), l'UICN est la catégorie mondiale de GBIF. À confirmer sur TAXREF et les
  listes régionales avant tout dépôt réglementaire.
- **Enjeu fort = espèce patrimoniale.** La règle littérale « toute espèce protégée = fort »
  classe des mésanges en enjeu fort ; elle reste en colonne `Enjeu réglementaire brut`.
- **GBIF est opportuniste** : il sous-représente les chiroptères, la flore protégée et les
  habitats. Une absence de donnée n'est pas une absence d'espèce.
- La sensibilité au solaire est un jugement d'expert générique, pas une base de données.
