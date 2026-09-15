# Guide du dépôt : où trouver quoi

Ce dépôt regroupe plusieurs outils d'analyse de territoire sous une même plateforme,
**ScruTech**. Ce fichier est la carte : pour chaque besoin, il te dit **quel fichier ouvrir**.

---

## À comprendre en premier (sinon rien n'a de sens)

Le moteur central, c'est **`scrutech/vegevigie/`**. C'est lui qui fait tourner presque tous
les outils (VegeVigie, PAFF, Écobuage, Biotrame).

Du coup, certains dossiers portent le nom d'un outil mais sont **presque vides** : le code qui
s'exécute vraiment est ailleurs.

| Dossier au nom trompeur | Ce qu'il contient vraiment | Le vrai code qui tourne est ici |
|---|---|---|
| `scrutech/paff/` | des explications, un schéma | `scrutech/vegevigie/src/vegevigie/interface.py` |
| `scrutech/ecobuage/` | le calcul « pur » + des notes | `scrutech/vegevigie/src/vegevigie/ecobuage_aoi.py` |
| `scrutech/biotrame/` | le calcul « pur » (grille, score) | `scrutech/vegevigie/src/vegevigie/biotrame_aoi.py` |

> **Règle simple :** un fichier en `..._aoi.py` = « lance l'outil sur une zone ».
> Les autres fichiers à côté = les briques de calcul qu'il assemble.

---

## Lancer un outil : 2 portes d'entrée, pas plus

1. **En ligne de commande** : la commande `vegevigie` (définie dans `scrutech/vegevigie/`).
   Exemple pour une démo rapide : `vegevigie run --small`.
2. **En un clic dans QGIS** : l'extension dans `scrutech/vegevigie/qgis_plugin/`.

Tout le reste n'est appelé que par ces deux portes.

---

## Où est le code de chaque outil

Pour chaque outil : le fichier qui **le lance sur une zone**, puis les fichiers de **calcul**
qu'il utilise.

| Outil | Fichier qui le lance | Briques de calcul |
|---|---|---|
| **VegeVigie** (verdissement, sécheresse) | `vegevigie/src/vegevigie/pipeline.py` | `trend.py`, `drought.py`, `seasonal.py`, `breaks.py` |
| **Biotrame** (zones prioritaires) | `vegevigie/src/vegevigie/biotrame_aoi.py` | `biotrame/src/biotrame/mesh.py`, `score.py`, `aggregate.py` ; `vegevigie/src/vegevigie/wetland.py` (zones humides) |
| **PAFF** (forêt ↔ maisons) | `vegevigie/src/vegevigie/interface.py` | `core/sources.py` (bâti, forêt) |
| **Écobuage** (aptitude au brûlage) | `vegevigie/src/vegevigie/ecobuage_aoi.py` | `ecobuage/ecobuage.py` ; `core/sources.py` (routes, bâti) |
| **AlphaEarth** (changement annuel) | `alphaearth/src/alphaearth/pipeline.py` | `client.py`, `change.py`, `classifier.py` |
| **SDBPi** (bâtiments vides) | `sdbpi/run_vacancy.py` | `sdbpi_processing.py`, `sdbpi_sources.py` |
| **Mini data centers** (choix de sites) | `mini_dc/outil/run.py` | `mini_dc_pipeline.py`, `mini_dc_checks.py` |
| **Climate Risk** (fournisseurs, EUDR) | `climate_risk_analyzer/` (plugin QGIS) | prototype |

*(Tous ces chemins sont sous `scrutech/`.)*

---

## Le socle commun : `scrutech/core/src/core/`

Réutilisé par **tous** les outils. Si tu ne dois retenir qu'un dossier, c'est celui-là.

| Fichier | Rôle en une phrase |
|---|---|
| `aoi.py` | comprend la zone qu'on lui donne (code INSEE, boîte, polygone) |
| `sources.py` | va chercher la donnée publique (bâti, forêt, réservoirs de biodiversité) |
| `io.py` | lit et écrit les fichiers de données géo |
| `db.py` | la petite base de données spatiale (DuckDB) |
| `storage.py` | range les résultats de façon ordonnée |
| `cog.py` | lit les rasters « allégés » (cloud), sans tout télécharger |
| `constants.py` | les repères communs (systèmes de coordonnées) |

Les scripts qui **préparent la donnée** (téléchargement, création de la base, publication dans
le cloud) et le schéma de la base (`schema.sql`) sont à part, dans `scrutech/data_setup/`.

---

## Nommage : deviner un chemin

- **Dossier d'outil** : le nom court de l'outil, en minuscules (`vegevigie/`, `biotrame/`,
  `paff/`, `mini_dc/`). Exception : l'extension QGIS nomme ses algorithmes PAFF `paf_*`.
- **Paquet Python installable** : `<outil>/src/<outil>/` + `pyproject.toml` (`core`, `biotrame`,
  `alphaearth`, `vegevigie`). Exception voulue : `ecobuage/ecobuage.py` reste un fichier
  unique, embarqué tel quel dans l'extension.
- **Projets à plat** (`sdbpi/`, `mini_dc/outil/`) : modules partagés préfixés `<outil>_*.py` ;
  scripts lançables nommés par un verbe anglais (`run.py`, `run_vacancy.py`, `download_arcep.py`).
- **Lancer un outil sur une zone** : `<outil>_aoi.py`.
- **Noms de fichiers `.py`** : en anglais.
- **Docs** : un `README.md` par dossier. Les noms conventionnels (`README`, `GUIDE`, `SECURITY`,
  `INSTALLATION`, `TODO`, `CLAUDE`) sont en MAJUSCULES, tous les autres docs en minuscules
  (`schema_bdd.md`, `tvb_sources.md`).

---

## Les documents du dépôt, et à quoi ils servent

| Fichier | À quoi il sert |
|---|---|
| `README.md` | la vitrine : page d'accueil publique |
| `GUIDE.md` | **ce fichier** : la carte pour s'y retrouver dans le code |
| `SECURITY.md` | la politique de sécurité |
| `scrutech/INSTALLATION.md` | comment un tiers utilise l'outil sans télécharger des Go de données |
| `scrutech/vegevigie/qgis_plugin/TODO.md` | le suivi à jour de l'extension QGIS (ce qui est fait, ce qui reste) |
| `scrutech/apprentissage/prompts/` | les prompts et cahiers des charges d'origine (archives : ils ne décrivent pas l'état actuel) |

---

## Ce que tu peux ignorer

- Les dossiers `*/tests/` : les tests automatiques (utiles à la machine, pas à la lecture).
- Les dossiers `*/src/` : simple convention Python, le code y est rangé « proprement ».
- `*/.venv/`, `__pycache__/` : environnement Python et cache, jamais à lire.
- `scrutech/apprentissage/` : mes notes, brouillons et prompts d'origine.
