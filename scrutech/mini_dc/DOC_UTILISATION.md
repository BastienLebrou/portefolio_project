# Document d'utilisation — Mini Data Center Selector

Outil d'identification automatique des parcelles aptes à recevoir un mini data
center résidentiel (boîtier 36 kVA, fibre, bruit 60 dB), à partir de 5 filtres
spatiaux, avec scoring et heatmap. Démo sur **Alba-la-Romaine (07400)**.

---

## 1. Ce que fait l'outil (en une phrase)

Il part de **toutes** les parcelles d'une commune, en élimine celles qui ne
conviennent pas via 5 filtres successifs (foncier → nuisances → fibre → énergie
→ réglementaire), **note** les survivantes de 0 à 100, et produit des **couches
cartographiques** pour décider où déployer en priorité.

---

## 2. Prérequis & installation

- **Python 3.11+**
- Dépendances :

```bash
cd _data_center_sig/outil
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate sur Linux/Mac)
pip install -r requirements.txt
```

Les extensions DuckDB `spatial` et `h3` se téléchargent toutes seules au premier
lancement (connexion internet requise une fois).

---

## 3. Démarrage rapide

```bash
python run.py
```

Cette commande **génère** les données synthétiques, **exécute** le pipeline,
**valide** (8 tests) et **écrit les livrables**. Durée : < 2 secondes.

### Options

| Commande | Effet |
|---|---|
| `python run.py` | Tout : (re)génère les données puis exécute le pipeline |
| `python run.py --no-generate` | Réutilise les données déjà présentes dans `data/raw/` |
| `python run.py --quiet` | Moins de logs |

---

## 4. Lire les résultats (console)

À chaque exécution, la console affiche :

1. **L'entonnoir de filtrage** — combien de parcelles survivent à chaque étape
   (ex. 484 → 324 → 98 → 65 → 44 → 31) et le taux de rétention.
2. **Le classement** — répartition `Premium` / `Bon` / `Moyen` + score moyen.
3. **Les 8 tests de validation** — tous doivent être `[OK ]`.
4. **La couche de contrôle** — combien de parcelles rejetées à chaque étape.

---

## 5. Les livrables (`data/outputs/`)

| Fichier | Contenu | Usage |
|---|---|---|
| `parcelles_eligibles.parquet` | Parcelles retenues + scores (Lambert-93) | analyse SIG |
| `parcelles_eligibles.geojson` | Idem en WGS84 | cartographie web |
| `parcelles_eligibles.csv` | Idem sans géométrie | tableur |
| `top20_premium.csv` | 20 meilleures parcelles | prospection commerciale |
| `heatmap_quartiers.geojson` | Densité d'éligibles par cellule H3 | ciblage de quartiers |
| `performance.json` | Compteurs + durées + résultats des tests | suivi / audit |
| `sig/*.parquet` | **9 couches de contrôle QGIS** | vérification visuelle |

---

## 6. Contrôle visuel dans QGIS

Voir [outil/GUIDE_CONTROLE_SIG.md](outil/GUIDE_CONTROLE_SIG.md). En résumé :
charge `data/outputs/sig/parcelles_qa.parquet`, style **catégorisé** sur le champ
`etape_rejet` → tu vois immédiatement, en couleur, pourquoi chaque parcelle est
acceptée ou rejetée, superposé aux contraintes (ABF, PPRI, EBC) et aux réseaux.

---

## 7. Ajuster les règles métier

Tout se règle dans [outil/config.py](outil/config.py), sans toucher au code :

| Paramètre | Défaut | Rôle |
|---|---|---|
| `SURFACE_LIBRE_MIN_M2` | 50 | espace libre minimal sur la parcelle |
| `BUFFER_NUISANCE_M` | 5 | recul intérieur (bruit 60 dB) |
| `DIST_MAX_BATIMENT_M` | 15 | longueur max de tirage des câbles |
| `FIBRE_STATUTS_OK` | Déployé, Raccordable | statuts fibre acceptés |
| `PUISSANCE_MIN_KVA` | 36 | capacité électrique requise |
| `ABF_BUFFER_M` | 500 | périmètre Monuments Historiques |
| `CLASSE_PREMIUM_MIN` / `BON_MIN` | 90 / 70 | seuils de classement |

Modifie, relance `python run.py` : toutes les couches sont régénérées.

---

## 8. Données réelles

Voir [outil/DONNEES_REELLES.md](outil/DONNEES_REELLES.md). On dépose les fichiers
publics (cadastre, BD TOPO, ARCEP, Enedis, Géorisques…) dans
`data/sources_reelles/`, on lance `python adapter_donnees_reelles.py`, puis
`python run.py --no-generate`.

---

## 9. Dépannage

| Symptôme | Cause / solution |
|---|---|
| `UnicodeEncodeError` | Console Windows cp1252 — déjà géré (sortie forcée en UTF-8) |
| `h3 ... not found` | Pas d'internet au 1er lancement ; relancer une fois connecté |
| `Tests : ÉCHEC` | Un invariant est cassé ; lire quel test est `[KO!]` et son détail |
| 0 parcelle éligible | Seuils trop stricts dans `config.py`, ou données d'entrée vides |

---

## 10. Passage à l'échelle (France)

L'architecture est **déjà optimisée** : DuckDB en base, jointures par **index
H3**, **entonnoir** (chaque filtre travaille sur moins de lignes), partition
`dept`. Pour traiter un département réel : déposer les données via l'adapter et
relancer — aucun changement de code. Voir [EXPLICATION_CODE.md](EXPLICATION_CODE.md)
pour le pourquoi de ces choix.
