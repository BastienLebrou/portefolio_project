---
type: systeme
---

# 🛰️ Veille GeoAI

Synthèses de l'agent Grok (IA géospatiale, télédétection, LiDAR, outils IA),
rangées par Claude. Règles de rangement : [[Conventions]].

## Derniers rapports

```dataview
TABLE periode_debut AS "Du", periode_fin AS "Au", nb_intel AS "Infos"
FROM "veille-geoai/10 Rapports"
SORT periode_fin DESC
LIMIT 10
```

## Intel à fort impact, pas encore testées

```dataview
TABLE date, themes, statut
FROM "veille-geoai/20 Intel"
WHERE impact = "haut" AND statut != "teste" AND statut != "archive"
SORT date DESC
```

## Par thème

```dataview
TABLE rows.file.link AS "Intel"
FROM "veille-geoai/20 Intel"
FLATTEN themes AS theme
GROUP BY theme
SORT length(rows) DESC
```

## Acteurs les plus cités

```dataview
TABLE length(file.inlinks) AS "Mentions", categorie
FROM "veille-geoai/30 Entités"
SORT length(file.inlinks) DESC
LIMIT 15
```

> Les tableaux demandent le plugin communautaire **Dataview**. Sans lui, la navigation
> par liens et la vue graphe marchent quand même.
