# QGIS_PLUGIN.md — Extension QGIS ScruTech

> Professionnalisation de l'extension QGIS **native ScruTech** déjà présente dans le
> dépôt. Objectif : rendu pro dans l'usage **et** dans la structure. **Commence par
> lire l'extension existante et restituer son état à Bastien avant de la refondre.**

---

## Rappel garde-fou

Cette extension est **100 % ScruTech**. Elle ne réutilise **aucun** code, asset ou
pattern d'un plugin d'employeur. Si tu vois du code dont l'origine est douteuse → stop,
tu demandes.

---

## Structure cible (standard QGIS plugin pro)

```
qgis_plugin/scrutech/
├── __init__.py
├── metadata.txt            # nom, version, description, tags, qgisMinimumVersion
├── plugin.py               # classe principale, hooks initGui/unload
├── resources.qrc           # ressources (icônes) compilées
├── ui/                     # .ui Qt Designer + logique associée
│   ├── main_dialog.ui
│   └── main_dialog.py
├── core/                   # logique métier (aucune dépendance à l'UI)
│   ├── acquire.py
│   ├── process.py
│   └── serve.py
├── icons/                  # SVG/PNG (palette ScruTech)
├── i18n/                   # traductions
├── test/                   # tests unitaires (pytest-qgis)
└── help/                   # documentation utilisateur
```

**Séparation stricte UI / core** : le `core/` ne doit jamais importer de Qt. Il doit
être exécutable hors QGIS (pour les tests et pour réutiliser la logique côté serveur).

---

## Qualité — rendu professionnel

**Structure :**
- `metadata.txt` complet et à jour (version sémantique, `qgisMinimumVersion`, tags, homepage).
- Chargement/déchargement propre (`initGui`/`unload`), pas de fuite de ressources.
- Barre d'outils + entrées de menu cohérentes, icônes en palette ScruTech.
- Gestion d'erreurs remontée à l'utilisateur via `QgsMessageBar`, jamais un crash silencieux.
- Traitements longs en tâche asynchrone (`QgsTask`) avec barre de progression — jamais
  de gel de l'UI.

**Usage :**
- Un panneau clair par pilier (VegeVigie / PAF / mini data centers) ou un assistant
  guidé étape par étape.
- Paramètres par défaut sensés (AOI, seuils), pré-remplis.
- Sorties documentées : couches nommées explicitement, styles QML appliqués automatiquement.
- Bouton d'aide → `help/`.

**Code (discipline ponytail) :**
- Réutilise les API QGIS/PyQGIS natives avant d'écrire du custom.
- Pas d'abstraction spéculative « au cas où ». Le plugin fait ce que les 3 piliers
  demandent, rien de plus.
- `core/` partagé avec le reste de ScruTech quand c'est possible (ne duplique pas la
  logique de traitement déjà écrite dans `src/`).

---

## Icônes

Palette ScruTech (le logo existe déjà dans le dépôt — reprends off-white / vert forêt /
bordeaux). Format badge carré arrondi, glyphe lisible à petite taille, cohérence entre
tous les boutons de la barre d'outils.

**Doute de continuité à lever** : reprend-on la palette du logo ScruTech existant à
l'identique, ou Bastien veut-il une charte d'icônes distincte pour le plugin ?

---

## Tests & packaging

- Tests avec `pytest` + `pytest-qgis` sur le `core/` (sans UI).
- Vérifie le chargement du plugin dans une session QGIS headless.
- Packaging : zip installable + éventuelle soumission au dépôt de plugins QGIS
  (à valider — c'est un acte public, donc décision Bastien).
