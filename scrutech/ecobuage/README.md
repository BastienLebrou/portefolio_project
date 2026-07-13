# Écobuage — aptitude au brûlage dirigé (analyse multicritère SIG)

Identifier et hiérarchiser les zones pertinentes pour l'écobuage sur un territoire
pastoral. Méthodologie reproductible : pile de rasters-critères alignés → scoring
pondéré 0-100 → 3 classes → GeoTIFF ouvrable en SIG.

Le prompt d'origine : [`PROMPT.md`](PROMPT.md). Le moteur de scoring : [`ecobuage.py`](ecobuage.py).

> Réutilise VégéVigie pour les indices satellite (NDVI, NBR, tendance, sécheresse) —
> ce module ne fait que l'étape de scoring, il consomme des critères déjà normalisés.

## 1. Couches nécessaires

| Couche | Source | Résolution | Rôle |
|---|---|---|---|
| NDVI / NBR / sécheresse | Sentinel-2 L2A (VégéVigie), Landsat | 10-20 m | biomasse sèche, assèchement, type de végétation |
| Tendance NDVI pluriannuelle | VégéVigie (Mann-Kendall) | 10-60 m | embroussaillement (recolonisation ligneuse) |
| Occupation du sol | Corine Land Cover, données pastorales | 100 m / vecteur | cibler landes, pelouses, parcours, friches, estives |
| MNT (pente, exposition, altitude) | RGE ALTI (IGN), Copernicus DEM | 1-30 m | pente = propagation + faisabilité |
| Historique feux | BDIFF, EFFIS | vecteur | récurrence, sensibilité |
| Contraintes / enjeux | Natura 2000, réserves, cadastre bâti, BD TOPO routes | vecteur | exclusions, accessibilité |
| Météo / climat | Météo-France, indices sécheresse | maille | fenêtres de brûlage |

## 2. Critères d'aptitude pondérés

Poids sommant à 100. Chaque critère est ramené en 0..1 avant pondération
(`rescale` / `band` dans [`ecobuage.py`](ecobuage.py)).

| Critère | Poids | Transformation | Seuils |
|---|---:|---|---|
| Végétation combustible / biomasse sèche | 25 | croissante | NDVI 0.2-0.5 (sec/rase) ; NBR bas = biomasse sénescente |
| Embroussaillement / recolonisation ligneuse | 25 | croissante | NDVI 0.4-0.7 **en hausse pluriannuelle** sur lande/parcours |
| Pente exploitable | 20 | bande | optimale 15-40 % ; rampe 10→60 % (trop plat inutile, >60 % infaisable) |
| Accessibilité (réseau routier) | 15 | décroissante (distance) | 0 m = 1, ≥ 500 m = 0 |
| Historique feux (récurrence) | 15 | croissante | plus la récurrence est forte, plus la sensibilité justifie la gestion |

**Exclusions (masque dur → score 0, classe « à exclure ») :**
- proximité habitat / infrastructures (< buffer sécurité, p.ex. 100 m) ;
- Natura 2000, réserves, forte sensibilité biodiversité ;
- hors landes / pelouses / parcours / friches (selon CLC).

## 3. Analyse multicritère (scoring 0-100)

```
aptitude = Σ(critère_0..1 × poids) / Σ(poids) × 100     # puis 0 si exclusion
```

`aptitude()` fait la somme pondérée, `classify()` applique les seuils. Toutes les
couches doivent partager la même grille/CRS (aligner via VégéVigie ou
`rasterio.warp.reproject` en amont). Export : `write_geotiff()` → un `.tif`
directement ouvrable dans QGIS/ArcGIS.

## 4. Hiérarchisation en 3 classes

| Classe | Aptitude | Justification |
|---|---|---|
| **Prioritaire** | ≥ 66 | Fort embroussaillement + biomasse sèche + pente exploitable + accessible, sans enjeu sensible. |
| **À étudier** | 33-66 | Aptitude partielle (p.ex. bonne végétation mais accès difficile, ou pente limite) — nécessite visite terrain. |
| **À exclure** | < 33 ou masqué | Enjeu sensible, trop plat/raide, végétation non combustible, ou proximité habitat/Natura. |

## 5. Périodes optimales & précautions

- **Fenêtre saisonnière** : fin d'automne → hiver (végétation dormante, sol humide en
  profondeur, biomasse aérienne sèche), avant reprise végétative.
- **Fenêtre météo** : vent faible-modéré **établi** (direction stable), pas de
  sécheresse extrême du sol, hygrométrie suffisante.
- **Précautions par zone** :
  - pente forte → ligne d'appui + équipes en aval, contre-feu maîtrisé ;
  - proximité enjeux → pare-feu, autorisation préfectorale, information riverains ;
  - Natura 2000 limitrophe → hors période sensible pour la faune.

## 6. Lancer

```bash
python ecobuage.py          # self-check sur données synthétiques
```

En production : alimenter `aptitude()` avec les rasters-critères réels (issus de
VégéVigie + MNT + CLC + historique), puis `classify()` et `write_geotiff()`.

## Livrables couverts

- [x] Tableau des critères et pondérations (§2)
- [x] Méthodologie SIG reproductible : indices, formules, seuils (§1-3), code Python
- [x] Scoring 0-100 → carte d'aptitude, export GeoTIFF ouvrable en SIG (§3)
- [x] Hiérarchisation 3 classes justifiée (§4)
- [x] Périodes optimales & précautions (§5)
- [ ] Carte commentée + liste des zones prioritaires (coordonnées, surface) → nécessite
      une **emprise réelle et les données du territoire** (placeholder `[zone d'étude]`).
