# PAFF — Protection Automatisée des Feux de Forêt

> **🧭 Où est le vrai code ?** Ce dossier ne contient que la conception (schémas, notes). Le
> code qui **calcule l'interface forêt/bâti sur une zone** est
> [`../vegevigie/src/vegevigie/interface.py`](../vegevigie/src/vegevigie/interface.py).
> Carte complète du dépôt : [GUIDE.md](../../GUIDE.md).

Dossier de conception issu de la réflexion « Lead Geodata Engineer » : architecture
de données et pipelines d'analyse spatiale, avec un premier livrable implémenté —
le calcul de l'**interface habitat-forêt (WUI)**.

## Contenu

| Fichier | Description |
|---|---|
| [`architecture_3_sujets.md`](architecture_3_sujets.md) | Réflexion d'architecture pour 3 sujets stratégiques : PAFF, carrefours de biodiversité (graphes spatiaux), trame blanche (acoustique). Sources/API, stockage S3, libs & algos Python, restitution web, et le backbone commun. |
| [`interface_wui.md`](interface_wui.md) | Le premier module implémenté : calcul de la frontière forêt↔bâti (Wildland-Urban Interface) dans une emprise. Concept, algorithme, usage CLI, vérification. |
| [`schema_paff_interface.svg`](schema_paff_interface.svg) | Schéma d'implantation : des deux couches (forêt VégéVigie + bâti) à la boucle PAFF temps réel. |

## Où vit le code réellement exécutable

Le module `interface` fait partie du paquet `vegevigie` (embarqué tel quel dans l'extension
QGIS au moment du packaging) :

```
scrutech/vegevigie/
├── src/vegevigie/interface.py   # le module (fonctions pures + I/O)
├── src/vegevigie/config.py      # InterfaceConfig (contact_m, metric_crs)
├── src/vegevigie/cli.py         # commande `vegevigie interface`
├── config/default.yaml          # section interface:
└── tests/test_interface.py      # tests
```

## Statut

- [x] Réflexion d'architecture (3 sujets)
- [x] Schéma d'implantation PAFF / interface WUI
- [x] Module `interface` : frontière + bande de contact, clip sur emprise, exports GeoParquet + GeoJSON
- [x] Vérifié (venv projet, GeoPandas 1.1.4) : géométrie, clip AOI, exports, cas sans contact, CLI de bout en bout
- [ ] Segmentation de la frontière en tronçons priorisés (longueur × vulnérabilité VégéVigie × proximité bâti)
- [x] Tests pytest : `scrutech/vegevigie/tests/test_interface.py`
