---
type: rapport
source: grok
recu_le: 2026-09-23
periode_debut: 2026-09-20
periode_fin: 2026-09-23
nb_intel: 5
tags: [veille/geoai]
---

# GeoAI : le « where » entre dans les LLM — et INTERGEO vient de refermer

> [!summary] En une phrase
> Pas de nouveau foundation model ces 48 h : la valeur est dans **l'intégration LLM ↔ donnée spatiale** et dans **le matériel de capture** (LiDAR couleur) qui nourrira les modèles de 2027.

## Intel extraites

1. [[2026-09-22 - BigGeo Spatial Cloud dans ChatGPT et Claude]] · impact haut
2. [[2026-09-22 - ASEAN GeoAI Fusion 2026, Segrit3D champion]] · impact moyen
3. [[2026-09-21 - geoai-py 0.43.1]] · impact haut
4. [[2026-09-17 - INTERGEO 2026, TrueView 550 et GeoAI agentique]] · impact moyen
5. [[2026-09-21 - HEO 25 M$, PIESAT-2, Hyades]] · impact bas

## Contexte (hors fenêtre 72 h)

- [[Esri]] pousse GeoVLM et les embeddings ([[Prithvi EO]] 2.0, [[Clay]], [[TerraMind]], [[DOFA]]) et l'IA agentique dans ArcGIS.
- [[Google Earth AI]] / Planetary Prediction Engine (fin août) : chaîne prédictive autonome, de la recherche de données à l'entraînement.
- [[Overture Maps]] atteint 50 membres : « l'IA a besoin d'un fond de carte ouvert et interopérable ».

## Actions prioritaires (selon Grok)

1. **Aujourd'hui (30 min)** : installer `geoai-py` *ou* tester BigGeo (500 crédits) sur un cas réel → voir les notes Intel.
2. **Cette semaine** : tirer 2 idées d'INTERGEO (agent SIG+BIM, LiDAR couleur) et les relier à la stack actuelle.
3. **Veille continue** : [[Qiusheng Wu|@giswqs]], Cercana / *GeoAI and the Law*, blogs Esri GeoAI, arXiv `cs.CV` + `cs.AI` + « geospatial foundation », lettres Overture et Planetary Computer.

---

## Texte d'origine (Grok, non modifié)

> [!quote]- Déplier le rapport brut
> # GeoAI : le « where » entre dans les LLM — et INTERGEO vient de refermer
>
> Veille **20–23 septembre 2026**. Semaine dense : clôture d'INTERGEO (15–17 sept., Munich), intégration spatiale dans les assistants généralistes, outillage open-source et capteurs LiDAR. Peu de papers « droppés » ces 72 h ; l'actualité est surtout **produit + marché + événement**.
>
> ### 1. BigGeo AI dans ChatGPT et Claude (22 sept.)
> **Résumé.** La startup canadienne BigGeo annonce que son « Spatial Cloud » est disponible dans ChatGPT et Claude : questions en langage naturel sur des données spatiales licenciées / open / internes ; géocodage, jointures de proximité, ranking de sites. Compte neuf : 500 crédits gratuits. Exemple : classer 12 sites d'épicerie en Alberta (population, concurrence, constructibilité).
>
> **Pertinence.** C'est le basculement que tout le monde attend : le GIS n'est plus un logiciel à ouvrir, c'est une **couche d'outils** derrière un LLM. Risque : hallucination géographique si la donnée n'est pas gouvernée. Opportunité : prototyper un use-case métier sans stack ArcGIS/QGIS.
>
> **Actions.** Tester BigGeo avec un jeu de points réel (sites, clients, risques). Comparer la même question dans ChatGPT *vs* Claude. Lister 3 questions spatiales que votre métier pose encore dans Excel.
>
> ### 2. ASEAN GeoAI Fusion 2026 : 48 finalistes, use-cases terrain (22 sept.)
> **Résumé.** Clôture à Kuala Lumpur : 17 équipes ASEAN, >1 100 participants depuis le lancement. Champion : **Grabber** (Malaisie) avec *Segrit3D* — 3D + GeoAI pour le planning 5G. Autres prix : impact développement durable, spatial intelligence. Thèmes : catastrophes, climat, agriculture, urbanisme.
>
> **Pertinence.** Signale que le GeoAI « utile » se joue sur **contraintes physiques** (hauteur de bâtiments, végétation, couverture radio), pas seulement sur la classification d'images.
>
> **Actions.** Lire le pitch Segrit3D (planning réseau + obstacles 3D) et le mapper à un cas telecom / énergie. Suivre les comptes MCMC / équipes UM–UPM pour les démos.
>
> ### 3. `geoai-py` 0.43.1 (Qiusheng Wu) — 21 sept.
> **Résumé.** Mise à jour du package open-source qui unifie PyTorch, Transformers, segmentation models et données spatiales (imagerie, vecteur). Docs + notebooks + plugin QGIS. Auteur très suivi dans l'écosystème open GeoAI.
>
> **Pertinence.** Meilleur point d'entrée **gratuit** pour passer d'une démo Hugging Face à un workflow Sentinel / orthophoto / SAM, sans attendre Esri.
>
> **Actions.** `pip install geoai-py` et lancer un notebook segmentation (eau, bâtiments, arbres). Tester le plugin QGIS si vous n'êtes pas à l'aise en Python. Suivre @giswqs et le repo opengeos/geoai.
>
> ### 4. INTERGEO 2026 + LiDAR : TrueView 550, agentic GeoAI, twins
> **Résumé.** Salon refermé le 17 sept. ; les recaps arrivent encore. GeoCue lance le **TrueView 550** (portée jusqu'à 2 100 m, dual cam 20 MP, ~1 M pts/s à 120 m AGL) + lignée NDAA avec Ouster OS1 Max (couleur native). Sessions « Agentic AI Meets Geodata and BIM ». Topcon élargit le workflow capture → monitoring.
>
> **Pertinence.** Deux tendances se rejoignent : **densité LiDAR + couleur** (meilleur training set pour modèles 3D / Gaussian splats) et **agents** qui orchestrent GIS + BIM. Données plus riches = GeoAI plus entraînable.
>
> **Actions.** Relire les recaps INTERGEO (sessions agentic GeoAI / UAV LiDAR shallow water). Si vous captez déjà du LiDAR : évaluer un pipeline « cloud colorisé → embeddings / splats ». Surveiller NDAA / BABA si vous travaillez marchés US.
>
> ### 5. Constellations & funding : HEO 25 M$, PIESAT-2, Hyades
> **Résumé.** HEO (imagerie « flyby » d'objets en orbite) lève **25 M$** (Series B, 21 sept.) pour passer en GEO. La Chine a lancé les PIESAT-2 13–16 (19 sept., imagerie haute résolution / SAR selon sources). Côté soft, Hyades (Auckland) a levé ~1,25 M$ NZ pour fusionner sat / drone / radar en modèles « AI-ready » (assurance, agri, climat) — alpha.
>
> **Pertinence.** Plus de capteurs + plus de fréquences = besoin d'**ingénierie de données spatiales** avant le modèle. SSA (space situational awareness) devient un voisin du GeoAI terrestre.
>
> **Actions.** Si vous faites du risk modeling : regarder Hyades comme couche d'alignement multi-capteurs. Pour l'EO classique : noter PIESAT-2 comme source commerciale asiatique à tester quand les catalogues seront ouverts.
>
> ### Contexte utile (pas « 72 h » mais encore actionnable)
> - **Esri** pousse GeoVLM / embeddings (Prithvi EO 2.0, Clay, TerraMind, DOFA) et l'IA agentique dans ArcGIS — à piloter si vous êtes déjà dans l'écosystème.
> - **Google Earth AI / Planetary Prediction Engine** (fin août) : workflow prédictif autonome (data discovery → training).
> - **Overture Maps** à 50 membres : argument « l'IA a besoin de fond de carte ouvert et interopérable ».
>
> ## 🚀 Actions prioritaires
> 1. **Aujourd'hui (30 min)** : installer `geoai-py` *ou* tester BigGeo avec 500 crédits sur *un* use-case réel (sites, aléas, couverture).
> 2. **Cette semaine** : extraire 2 idées INTERGEO (agent GIS+BIM, LiDAR couleur) et les coller à votre stack actuelle.
> 3. **Veille continue** : @giswqs, Cercana / *GeoAI and the Law*, blogs Esri GeoAI, arXiv `cs.CV` + `cs.AI` + « geospatial foundation », newsletters Overture et Planetary Computer.
>
> *Honnêteté :* pas de foundation model majeur annoncé ces 48 h. La valeur est dans **l'intégration LLM ↔ donnée spatiale** et dans **le hardware de capture** qui alimentera les modèles de 2027.
