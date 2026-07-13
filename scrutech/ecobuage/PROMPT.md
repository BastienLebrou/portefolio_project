# Prompt — Zones d'écobuage (brûlage dirigé)

> Prompt d'origine du projet, archivé selon la convention du repo.

Tu es analyste géospatial spécialisé en gestion des milieux pastoraux et prévention
incendie. Objectif : identifier et hiérarchiser les zones les plus pertinentes pour
réaliser de l'écobuage (brûlage dirigé) sur le territoire suivant :
[zone d'étude / commune / coordonnées / emprise].

**Données à croiser :**

- **Imagerie satellite multispectrale (Sentinel-2, Landsat)** : calcule le NDVI et le
  NBR pour cartographier la densité et le type de végétation, repère l'embroussaillement
  (recolonisation ligneuse), la biomasse sèche et l'assèchement saisonnier.
- **Occupation du sol (Corine Land Cover, données pastorales)** : cible landes,
  pelouses, parcours, friches et zones d'estive en déprise.
- **Topographie (MNT)** : pente, exposition, altitude — la pente conditionne la
  propagation et la faisabilité du brûlage.
- **Historique des feux (base BDIFF / EFFIS)** : zones déjà brûlées, récurrence,
  sensibilité.
- **Contraintes réglementaires et enjeux** : proximité habitat/infrastructures, zones
  Natura 2000, réserves, sensibilité biodiversité, réseau routier (accès).
- **Météo/climat** : indice de sécheresse, régime de vent dominant, fenêtres de brûlage
  favorables.

**Méthode :**

1. Décris les couches nécessaires, leur source et leur résolution.
2. Définis des critères d'aptitude pondérés (végétation combustible, embroussaillement,
   pente exploitable, accessibilité, faible enjeu sensible, historique).
3. Propose une analyse multicritère (scoring 0-100) pour produire une carte d'aptitude à
   l'écobuage.
4. Hiérarchise les zones en 3 classes : prioritaires / à étudier / à exclure, avec
   justification.
5. Signale les périodes optimales de brûlage et les précautions par zone.

**Livrables attendus :** tableau des critères et pondérations, méthodologie SIG
reproductible via algorithmes python appelant des images satellites et en chargeant les
résultats sous format ouvrables par SIG (indices, formules, seuils), carte d'aptitude
commentée, et liste des zones prioritaires avec coordonnées et surface estimée.
