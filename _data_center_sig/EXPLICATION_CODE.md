# Explication vulgarisée du code

Public visé : tu connais **QGIS et un peu de Python**, mais pas forcément les
réflexes « geo-data engineer ». Ce document explique **comment** l'outil est
construit et surtout **pourquoi** ces choix — pas juste le quoi.

---

## 1. L'idée centrale : un « contrat » d'entrée

Imagine une **usine**. À l'entrée, un quai de déchargement où arrivent des
caisses au format standard. À l'intérieur, une chaîne qui ne sait traiter QUE ce
format. Peu importe d'où viennent les caisses (fournisseur A ou B), tant
qu'elles respectent le format du quai, l'usine tourne.

Ici :
- le **quai** = les fichiers `data/raw/*.parquet` (le « contrat »),
- le **fournisseur fictif** = `generate_synthetic.py` (données inventées),
- le **fournisseur réel** = `adapter_donnees_reelles.py` (cadastre, ARCEP…),
- la **chaîne** = `pipeline.py`.

→ On peut changer la source de données sans jamais toucher au pipeline. C'est le
premier réflexe d'ingénierie : **découpler** l'ingestion du traitement.

---

## 2. Pourquoi DuckDB (et pas GeoPandas tout seul) ?

GeoPandas charge tout en mémoire (RAM). Sur une commune, aucun souci. Sur la
**France (140 M de parcelles)**, ça explose.

**DuckDB** est une base analytique qui travaille **sur le disque, par morceaux**,
et qui a deux super-pouvoirs ici :
- l'extension **`spatial`** : les fonctions `ST_*` (surface, distance, buffer,
  intersection…) — comme PostGIS, mais sans serveur à installer ;
- l'extension **`h3`** : l'indexation hexagonale (voir §4).

Réflexe : **on garde le calcul DANS la base**. On n'aspire pas les données vers
Python pour les retraiter. Le code Python ne fait qu'**orchestrer** des requêtes.

`db.py` est le portier : il ouvre la base, charge les 2 extensions, crée les
schémas. Tout le monde passe par lui.

---

## 3. Les coordonnées : Lambert-93 vs WGS84

Piège classique du débutant SIG : calculer une **surface en degrés** (WGS84).
Résultat faux, parfois de 25 %.

Règle appliquée partout : **EPSG:2154 (Lambert-93)** pour toute mesure (surface,
distance, buffer), car c'est un système **métrique** adapté à la France. Le WGS84
n'est utilisé que pour l'export web (GeoJSON) et pour calculer les index H3 (qui
vivent sur la sphère). La conversion est faite à la volée par `ST_Transform`.

---

## 4. H3 : la trouvaille pour ne pas exploser

Problème : pour relier 140 M de parcelles à 5 M de bâtiments, l'approche naïve
teste **chaque parcelle contre chaque bâtiment** = des milliards de comparaisons.
Impossible.

**H3** (créé par Uber) découpe le monde en **hexagones** emboîtés. Chaque objet
reçoit l'identifiant de l'hexagone qui le contient (`h3_res9`). Pour trouver les
bâtiments d'une parcelle, on ne regarde que les bâtiments **du même hexagone et
des voisins immédiats** (`h3_grid_disk`), au lieu de tout l'univers.

Analogie : pour trouver tes voisins, tu ne sonnes pas à toutes les portes de
France — tu regardes **ton pâté de maisons**. H3 = le pâté de maisons.

Dans le code (`pipeline.py`), tu vois systématiquement :
```sql
JOIN ... ON list_contains(h3_grid_disk(p.h3_res9, k), autre.h3_res9)
       AND ST_Intersects(...)        -- test exact, seulement sur les candidats
```
Le H3 **présélectionne** (rapide), le `ST_*` **tranche** (exact). C'est le motif
« préfiltre grossier + test fin » — le cœur de l'optimisation.

> Sur Alba-la-Romaine (484 parcelles) ça n'a pas d'impact visible, mais le code
> est **déjà écrit pour la France**. C'est ça, « construire déjà optimisé ».

---

## 5. La chaîne en 3 couches (le fichier `pipeline.py`)

Comme en cuisine pro : on ne mélange pas l'épluchage et le dressage.

### Couche `staging` — on nettoie
On lit chaque fichier brut, on **valide les géométries** (`ST_IsValid`,
`ST_MakeValid`), on calcule la surface, on pose les index H3. Une table propre
par source (`stg_parcelles`, `stg_batiments`…).

### Couche `intermediate` — on relie
On associe chaque bâtiment à sa parcelle (jointure H3), on calcule l'**emprise au
sol**, puis la **surface libre** = surface parcelle − emprise. C'est la donnée
clé du filtre 1.

### Couche `marts` — on décide (les 5 filtres en « entonnoir »)
Chaque filtre est une table qui **ne garde que les survivants**. Donc le filtre 2
travaille sur moins de lignes que le filtre 1, le 3 moins que le 2, etc. C'est
voulu : **chaque étape allège la suivante**.

| Filtre | Question posée | Rejette si… |
|---|---|---|
| 1. Foncier | habitat individuel + place dispo ? | pas de maison, immeuble, ou < 50 m² libres |
| 2. Nuisances | recul de 5 m possible + câbles ≤ 15 m ? | parcelle trop étriquée |
| 3. Fibre | fibre déployée/raccordable à proximité ? | seulement ADSL / non desservi |
| 4. Énergie | poste électrique avec ≥ 36 kVA dispo ? | réseau saturé |
| 5. Réglementaire | hors ABF, hors zone inondable, hors EBC ? | dans une zone interdite |

Le filtre 5 utilise une **anti-jointure** : on liste les parcelles qui *touchent*
une contrainte (ABF 500 m, PPRI, EBC) puis on les exclut (`NOT IN`).

---

## 6. Le score (0–100) et les classes

Chaque filtre passé rapporte des points (0 à 20). On ajoute des **bonus** (+5)
de proximité : photovoltaïque, borne de recharge, poste électrique proche
(signes d'un réseau déjà costaud). Total **plafonné à 100**.

```
score = foncier + nuisances + fibre + énergie + réglementaire + bonus   (max 100)
```

Puis un classement commercial : **Premium** (≥ 90), **Bon** (≥ 70), **Moyen**.
Les seuils sont dans `config.py` — un survivant des 5 filtres est déjà bon, donc
on place la barre « Premium » haut pour distinguer l'élite.

Tous ces nombres (50 m², 5 m, 36 kVA, pondérations…) sont **centralisés dans
`config.py`** : aucune « valeur magique » perdue dans une requête. Changer une
règle = changer une ligne.

---

## 7. La heatmap (`fct_heatmap_quartiers`)

On regroupe les parcelles éligibles par **gros hexagone** (`h3_res8`, ~0,7 km² =
un « quartier ») et on compte combien de Premium par quartier. Résultat : une
carte de chaleur qui dit **où concentrer la prospection**. Les hexagones
proviennent de `h3_cell_to_boundary_wkt`.

---

## 8. La couche de contrôle SIG (`fct_parcelles_qa`)

C'est la couche qui te permet de **vérifier le travail de la machine**. Elle
contient **les 484 parcelles** (gardées ET rejetées), chacune annotée de
`etape_rejet` (à quel filtre elle est tombée). Chargée dans QGIS et coloriée,
elle rend l'entonnoir **visible** : on voit les parcelles ABF en violet, les
sans-fibre en orange, etc. C'est le réflexe « **un pipeline n'est pas fini tant
qu'on ne peut pas l'auditer** ».

Techniquement : des `LEFT JOIN` entre la base et chaque table de filtre ; si une
parcelle est absente de `fct_filtre_03_fibre`, c'est qu'elle est tombée à
l'étape 3.

---

## 9. Les tests (`tests_pipeline.py`)

8 vérifications qui DOIVENT être vraies, sinon le résultat est faux :
unicité des parcelles, géométries valides, score dans [0, 100], entonnoir
décroissant, cohérence de la heatmap, et surtout **« zéro éligible en zone
interdite »** (double sécurité du filtre 5). Le script renvoie un code d'erreur
si un test casse → on ne livre jamais un résultat non validé.

---

## 10. L'orchestrateur (`run.py`)

Le chef d'orchestre : il enchaîne génération → pipeline → tests → exports →
rapport `performance.json`, en **chronométrant**. Mesurer le temps et la
volumétrie fait partie du livrable (on saura tout de suite si ça dérape à
l'échelle).

L'export passe par un seul helper (`_wkb_gdf`) qui transforme une requête DuckDB
en couche GeoPandas, réutilisé pour tous les fichiers (principe **DRY** : ne pas
se répéter).

---

## 11. Ce qu'il faut retenir

1. **Découpler** ingestion et traitement (le « contrat » `data/raw/`).
2. **Calculer dans la base** (DuckDB), pas en RAM Python.
3. **Mesurer en mètres** (EPSG:2154), pas en degrés.
4. **Préfiltrer avec H3** avant tout test géométrique coûteux.
5. **Entonnoir** : chaque filtre allège le suivant.
6. **Tout paramétrer** dans `config.py`.
7. **Tester et auditer** (8 tests + couche QA) : pas de livraison à l'aveugle.
8. **Idempotence** (`CREATE OR REPLACE`) : on relance sans rien casser.

Ces 8 réflexes sont ce qui distingue un script jetable d'un **pipeline robuste,
déjà prêt pour l'échelle**.
