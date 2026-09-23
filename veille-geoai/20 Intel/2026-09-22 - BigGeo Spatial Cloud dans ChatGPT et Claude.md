---
type: intel
date: 2026-09-22
rapport: "[[2026-09-23 - Le where entre dans les LLM, INTERGEO refermé]]"
themes: [llm-spatial, marche]
entites: ["[[BigGeo]]"]
impact: haut
statut: a-tester
sources: []
---

# BigGeo Spatial Cloud dans ChatGPT et Claude

**Quoi.** [[BigGeo]] (startup canadienne) rend son « Spatial Cloud » utilisable depuis ChatGPT et Claude : questions en langage naturel sur des données spatiales (licenciées, ouvertes ou internes), géocodage, jointures de proximité, classement de sites. 500 crédits offerts à l'ouverture. Démo : classer 12 sites d'épicerie en Alberta (population, concurrence, constructibilité).

**Pourquoi ça compte.** Le SIG devient une couche d'outils derrière un LLM plutôt qu'un logiciel qu'on ouvre. Risque : hallucination géographique si la donnée n'est pas maîtrisée. Opportunité : prototyper un cas métier sans ArcGIS/QGIS.

**Lien ScruTech.** Même logique que ScruTech (« on désigne une zone, l'outil va chercher la donnée ») : BigGeo est à la fois un concurrent de posture et un banc de comparaison.

## Actions
- [ ] Tester BigGeo sur un jeu de points réel (sites, aléas, parcelles de prospection)
- [ ] Poser la même question dans ChatGPT et dans Claude, comparer les réponses
- [ ] Lister 3 questions spatiales encore traitées dans Excel
