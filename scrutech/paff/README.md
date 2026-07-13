# PAFF — Protection Automatisée des Feux de Forêt

Dossier de conception issu de la réflexion « Lead Geodata Engineer » : architecture
de données et pipelines d'analyse spatiale, avec un premier livrable implémenté —
le calcul de l'**interface habitat-forêt (WUI)**.

## Contenu

| Fichier | Description |
|---|---|
| [`architecture_3_sujets.md`](architecture_3_sujets.md) | Réflexion d'architecture pour 3 sujets stratégiques : PAFF, carrefours de biodiversité (graphes spatiaux), trame blanche (acoustique). Sources/API, stockage S3, libs & algos Python, restitution web, et le backbone commun. |
| [`interface_wui.md`](interface_wui.md) | Le premier module implémenté : calcul de la frontière forêt↔bâti (Wildland-Urban Interface) dans une emprise. Concept, algorithme, usage CLI, vérification. |
| [`schema_paff_interface.svg`](schema_paff_interface.svg) | Schéma d'implantation : des deux couches (forêt VégéVigie + bâti) à la boucle PAFF temps réel. |
| [`reference/interface.py`](reference/interface.py) | Copie de référence du module (snapshot). L'implémentation intégrée vit dans le package `vegevigie` de `portefolio_project`. |

## Où vit le code réellement exécutable

Le module `interface` a été intégré au package `vegevigie` packagé pour QGIS, dans le
repo imbriqué `portefolio_project` :

```
portefolio_project/vegevigie/qgis_plugin/scrutech/
├── vegevigie/interface.py      # le module (fonctions pures + I/O)
├── vegevigie/config.py         # InterfaceConfig (contact_m, metric_crs)
├── vegevigie/cli.py            # commande `vegevigie interface`
└── config/default.yaml         # section interface:
```

La copie sous [`reference/`](reference/interface.py) est un instantané, à titre de
documentation, pour que ce repo soit auto-suffisant.

## Statut

- [x] Réflexion d'architecture (3 sujets)
- [x] Schéma d'implantation PAFF / interface WUI
- [x] Module `interface` : frontière + bande de contact, clip sur emprise, exports GeoParquet + GeoJSON
- [x] Vérifié (venv projet, GeoPandas 1.1.4) : géométrie, clip AOI, exports, cas sans contact, CLI de bout en bout
- [ ] Segmentation de la frontière en tronçons priorisés (longueur × vulnérabilité VégéVigie × proximité bâti)
- [ ] Miroir `src/` + `tests/test_interface.py` en pytest
