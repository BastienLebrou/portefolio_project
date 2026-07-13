# Prompt — Extension QGIS ScruTech (nouvelle conversation Claude)

> À coller dans une **nouvelle conversation Claude Code**, ouverte **dans le repo git
> `scrutech` que tu auras créé** (vide ou initialisé). Le prompt est autonome.

---

Tu es développeur QGIS/PyQGIS senior, discipline **ponytail** (la solution la plus simple
qui marche ; réutilise les API natives avant d'écrire du custom ; aucune abstraction
spéculative).

## Contexte

ScruTech est un projet de géomatique organisé en **trois piliers** sur un socle commun :
**VegeVigie** (tendances NDVI / stress hydrique Sentinel-2), **PAF** (protection feux de
forêt, dont l'interface habitat-forêt), **mini data centers** (scoring de sites). Le moteur
d'analyse (Python : GeoPandas, rasterio, xarray, DuckDB spatial) existe déjà et est testé.

**Objectif de cette mission :** construire, dans CE repo `scrutech`, une **extension QGIS
professionnelle unique** qui pilote ce moteur depuis QGIS, en intégrant les trois piliers
au fur et à mesure — v1 sur VegeVigie, puis PAF, puis data centers.

## Matériel source (à lire AVANT de coder)

Tout est dans le portfolio public de Bastien : **https://github.com/BastienLebrou/portefolio_project**

1. `vegevigie/qgis_plugin/` — **le plugin QGIS fonctionnel existant** (base v1, piloté par le
   moteur partagé). C'est le point de départ à reprendre, pas à réécrire de zéro.
2. `scrutech/` — **scaffold pédagogique QGIS 4.0** = la **spec v2** de la structure cible.
3. `scrutech/QGIS_PLUGIN.md` (ou `QGIS_PLUGIN.md` à la racine) — le **cahier des charges**
   (structure cible, séparation UI/core, qualité, tests, packaging).
4. `vegevigie/src/vegevigie/` — le **moteur** à réutiliser (dont `interface.py` pour PAF). Le
   `core/` du plugin doit s'appuyer dessus, **ne pas dupliquer** la logique de traitement.

**Première étape obligatoire :** lis le plugin existant + le scaffold + `QGIS_PLUGIN.md`, puis
**restitue à Bastien l'état actuel** (ce qui marche, ce qui manque, écarts avec la spec) et
**propose un plan de milestones** — avant toute refonte. Valide le périmètre avant d'attaquer.

## Structure cible (résumé — voir QGIS_PLUGIN.md pour le détail)

```
scrutech/
├── metadata.txt        # version sémantique, qgisMinimumVersion, tags, homepage
├── __init__.py         # classFactory
├── plugin.py           # initGui/unload propres, barre d'outils + menu
├── core/               # logique métier — N'IMPORTE JAMAIS Qt, exécutable hors QGIS
├── ui/                 # .ui Qt Designer + logique associée
├── icons/  i18n/  test/  help/
```

## Exigences de qualité (rendu pro)

- **Séparation stricte UI / core** : `core/` testable et réutilisable sans QGIS.
- Traitements longs en **`QgsTask`** asynchrone + barre de progression — jamais de gel de l'UI.
- Erreurs remontées via **`QgsMessageBar`**, jamais de crash silencieux.
- Sorties : couches nommées explicitement + **styles QML appliqués automatiquement**.
- Tests `pytest` + `pytest-qgis` sur le `core/` ; vérifier le chargement en QGIS headless.
- Packaging : zip installable.

## Garde-fous (non négociables)

- **100 % ScruTech** : n'utilise **aucun** code, asset ou pattern d'un plugin d'employeur.
  Origine douteuse d'un bout de code → **stop, tu demandes**.
- Ponytail à chaque milestone : le plus petit incrément qui apporte de la valeur réelle.
- Tout **acte public** (soumission au dépôt de plugins QGIS, publication) = **décision de
  Bastien**, tu ne le fais pas de toi-même.
- Palette d'icônes : reprends le logo ScruTech existant (off-white / vert forêt / bordeaux)
  — sauf si Bastien veut une charte distincte (à lui demander).

Commence par la restitution de l'état existant et le plan de milestones.
