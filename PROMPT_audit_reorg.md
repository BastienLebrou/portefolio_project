# Prompt — Audit & réorganisation vers backend / S3 / BDD

> À coller dans une **nouvelle conversation Claude Code**, ouverte à la racine du repo
> `portefolio_project`. Autonome.

---

Tu es Lead Geodata Engineer & architecte de données, discipline **ponytail** (le plus
petit socle qui marche ; stdlib/natif avant dépendances ; pas d'abstraction spéculative).

## Contexte

Ce monorepo réunit plusieurs projets SIG : **vegevigie** (télédétection Sentinel-2 :
tendances NDVI, sécheresse), **paff** (interface habitat-forêt / feux), **sdbpi**
(bâtiments professionnels inoccupés, BD TOPO × SIRENE), **ecobuage** (scoring
multicritère de brûlage), **_data_center_sig** (sélection de sites), et un **plugin QGIS
« ScruTech »** (hub) dans `vegevigie/qgis_plugin/`.

**Problème constaté (test QGIS réel).** Les front-ends tentent de faire tourner les
pipelines lourds (odc-stac, xarray, rasterio, geopandas…) **dans le Python de QGIS** →
échec (stack absente, conflits GDAL). Chaque projet est un silo qui mélange acquisition,
calcul, données et restitution.

## Cible : 3 couches nettes (la stack imposée dès l'origine)

1. **Backend / batch** — des scripts Python (la stack lourde) qui **acquièrent + calculent
   en fond** (CLI / planifié), **sans dépendre de QGIS**.
2. **Stockage** — un data lake objet (**S3**, ou local d'abord) : **COG** pour le raster,
   **GeoParquet** pour le vecteur ; et une base **interrogeable** — **DuckDB spatial
   d'abord** (fichier, zéro serveur), **PostGIS** seulement si le multi-utilisateur / temps
   réel le justifie.
3. **Front-ends fins** — plugin QGIS, dashboards, WebGIS → ils **LISENT** les couches déjà
   calculées depuis la BDD / S3. **Aucun calcul lourd côté QGIS.**

## Tâches

**A. AUDIT (d'abord — ne déplace rien).** Parcours chaque dossier et rends un tableau par
projet : entrées (sources/API), sorties (fichiers/formats), dépendances, point d'entrée,
et classe chaque partie en `{acquisition | calcul | donnée | restitution}`. Repère les
duplications, le code mort, les données à ne pas versionner (`analyse_financiere` =
privé), et ce qui tourne déjà en CI (`vegevigie/**`).

**B. CIBLE.** Propose une arbo monorepo, p.ex. :
`core/` (utils partagés : accès S3, accès BDD, IO COG/GeoParquet) · `pipelines/<projet>/`
(backend batch) · `storage/` (schéma BDD + loaders + layout S3) · `frontends/qgis/` ·
`frontends/dashboard/` · `infra/` (planification). Définis le **schéma BDD** (tables par
territoire / produit) et le **layout S3** (partitionnement), plus le **contrat de lecture**
des front-ends : *une couche = une requête BDD ou un chemin S3*.

**C. EXÉCUTE** la réorg par **petits incréments réversibles** : déplace, adapte les
imports, garde la **CI verte**, un commit par étape. Le plugin QGIS devient un simple
**lecteur** (il charge les COG/GeoParquet produits par le backend, ou interroge
DuckDB/PostGIS) — retire la logique de calcul lourde du plugin. Les algorithmes ScruTech
qui n'ont pas besoin de la stack (PAF, écobuage : natifs QGIS) peuvent rester côté plugin.

## Garde-fous (non négociables)

- **ponytail** : DuckDB avant PostGIS, local avant S3, pas d'abstraction spéculative. Le
  plus petit socle qui sert les 5 projets ; ne duplique pas ce qui existe.
- Ne publie **pas** `analyse_financiere/` (privé) ; respecte l'allowlist `.gitignore`.
- **Identifiants S3/BDD jamais en clair** dans le repo (variables d'environnement / config
  gitignorée). Ne crée **pas** de bucket/base de toi-même — propose, Bastien exécute les
  actes cloud.
- Aucune suppression destructive sans l'accord de Bastien.

**Première étape :** rends-moi l'**AUDIT** (tableau par projet) + l'**arbo cible** + le
**schéma BDD / layout S3**, et **valide le périmètre** avec moi **avant** de déplacer quoi
que ce soit.
