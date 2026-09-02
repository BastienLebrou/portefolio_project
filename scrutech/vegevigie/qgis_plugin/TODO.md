# TODO — Plugin QGIS ScruTech (mise en release)

> Suivi d'exécution avant mise à disposition du plugin comme fonctionnalité utilisable.
> Complète `QGIS_PLUGIN.md` (racine, cahier des charges) — ce fichier est la checklist
> vivante. Dernière mise à jour : 2026-09-01, suite au point avec Bastien.

## État des points soulevés (session du 2026-09-01)

1. **Test sur une autre machine** — Bastien teste sur un autre poste cette semaine.
   Rien à faire de mon côté avant son retour ; le packaging (§ ci-dessous) doit être prêt
   pour ce test.
2. **Build de packaging** — voir § Packaging & sécurité.
3. **Tests plugin (pytest-qgis / chargement QGIS headless)** — Bastien s'en charge
   prochainement. Pas d'action pour l'instant, cf. `QGIS_PLUGIN.md` § Tests & packaging
   pour le cahier des charges.
4. **Test bootstrap** — voir § Bootstrap.
5. **Vraie TVB régionale (biotrame)** — déjà désactivée par défaut : le pilier reste sur le
   proxy proximité tant que `SCRUTECH_TVB_WFS` (ou le paramètre d'algo) n'est pas
   renseigné (voir `scrutech/biotrame/TVB_SOURCES.md`). Rien à coder — reste en TODO
   pour validation du endpoint AURA depuis un réseau non restreint.
6. **Scaffold `scrutech/plugin/` (spec v2, QGIS 4.0, STAC/SAR)** — mis en pause. Sera
   repris plus tard comme fonctionnalité à part, avec son propre branding — pas fusionné
   dans le hub v1 (`vegevigie/qgis_plugin/`).
7. **Points en suspens** (palette icônes, `experimental=True`, version `0.4.0`, soumission
   au dépôt officiel QGIS) — actés comme non bloquants pour une v1 de test. À trancher au
   moment de la publication publique, pas avant.

---

## Packaging & sécurité

### Build
- [ ] Rebuild `dist/scrutech.zip` juste avant le test externe (`python qgis_plugin/package.py`).
- [ ] Vérifier le contenu du zip avant envoi : engine + config bundlés, **aucun** fichier
      `analyse_financiere/`, secret, clé API ou `.env` dedans (garde-fou CLAUDE.md §2.2).
- [ ] Documenter dans `qgis_plugin/README.md` la procédure exacte testée : Install from
      ZIP → redémarrage QGIS → où pointer le Python externe.
- [ ] Noter par build testé : date, machine, résultat (pass/fail + ce qui a coincé) — même
      un simple historique en bas de ce fichier suffit, pas besoin d'outil dédié.

### Sécurité — pour tout téléchargement déclenché par le plugin (deps actuelles ET futurs
modèles GeoAI, § plus bas)

Rien de tout ça n'est optionnel dès qu'un `requests.get`/`urlretrieve` apparaît dans le
plugin — c'est le patch d'attaque le plus probable pour une extension distribuée
publiquement :

- **HTTPS uniquement**, vérification TLS jamais désactivée (`verify=False` interdit).
- **URLs pinnées en dur** dans le code — jamais une URL de modèle/dépendance construite
  depuis une entrée utilisateur non validée, jamais de redirection vers un miroir tiers.
- **Checksum SHA-256 obligatoire**, vérifié avant toute utilisation du fichier — sinon rejet
  silencieux et message clair, jamais un "on l'utilise quand même".
- Cache de téléchargement **hors du repo git et hors du dossier plugin versionné** (dossier
  profil QGIS utilisateur, type `~/.scrutech/models/`) — jamais commité, jamais bundlé
  dans le zip (une AOI de 2 Go de poids modèle ferait exploser le zip et le dépôt).
- **Aucune exécution de code arbitraire depuis un artefact téléchargé** : préférer
  `.safetensors`/ONNX à un `.pt`/`.pth` pickle. Si `torch.load` est utilisé quand même,
  forcer `weights_only=True` — le format pickle par défaut de PyTorch permet une RCE au
  chargement, ce n'est pas une hypothèse théorique, c'est un vecteur connu de
  l'écosystème ML.
- **Toujours informer avant de télécharger** : taille, source, licence — jamais de
  téléchargement silencieux de plusieurs centaines de Mo/Go sans confirmation explicite
  (même règle que les gros téléchargements Sentinel-2, déjà actée en CLAUDE.md §10 côté
  `vegevigie`).
- Téléchargement en tâche asynchrone (`QgsTask` ou équivalent Processing `feedback`),
  jamais bloquant l'UI QGIS.
- **Licence de chaque modèle vérifiée et citée explicitement** avant toute intégration —
  garde-fou CLAUDE.md §2.1 : uniquement de l'open véritable (Apache-2.0/MIT type), jamais
  un modèle "recherche uniquement" ou à licence ambiguë. Vérifier au moment de
  l'intégration, pas sur la base d'un souvenir — les dépôts HuggingFace changent parfois
  de licence entre deux versions.

---

## Bootstrap test

Objectif : un nouveau testeur (autre machine, zéro contexte) ne doit jamais se retrouver
face à une stacktrace brute au premier essai.

- [ ] Nouvelle entrée plugin — **"ScruTech ▸ Vérifier l'installation"** — qui exécute un
      self-check complet et rapporte un pass/fail lisible pour :
  - version QGIS (`qgisMinimumVersion`/`qgisMaximumVersion` respectés) ;
  - interpréteur Python détecté (interne QGIS ou externe pointé) ;
  - dépendances datacube (**réutiliser `dependencies.py` existant** — ne pas dupliquer
    `missing_dependencies()`/`install_hint()`, ils font déjà exactement ça) ;
  - espace disque disponible (cache modèles + data) ;
  - accès réseau aux sources utilisées (Planetary Computer aujourd'hui, sources de
    modèles GeoAI demain).
- [ ] Doit pouvoir tourner **avant** tout autre bouton du plugin — zéro configuration
      cachée prérequise, message d'erreur actionnable (le chemin `pip install` exact, pas
      juste "ImportError").

---

## GeoAI

Liste complète d'idées et point d'implantation par pilier : voir le message de chat du
2026-09-01 (pas dupliqué ici pour éviter deux sources qui divergent). Bastien a arbitré :
**SAM (segmentation générale) en premier.**

### Livré (2026-09-02) — MVP "Segment anything (SAM, experimental)"
- Nouvel algorithme Processing, groupe **7 · GeoAI (modèles ouverts)** :
  `qgis_plugin/scrutech/algorithms/geoai_segment.py`.
- Moteur : `vegevigie/src/vegevigie/geoai_segment.py` — télécharge le checkpoint SAM
  ViT-B (Apache-2.0, ~375 Mo) une fois, **pin le sha256 en TOFU** (Meta ne publie aucun
  hash officiel — documenté dans le module, pas de hash inventé), le vérifie à chaque
  réutilisation. Dossier cache `~/.scrutech/models/`, hors repo, hors dossier plugin.
- Dépendance **optionnelle** : `uv sync --extra geoai` (torch + `segment-geospatial`),
  n'affecte ni l'install de base ni la CI existante.
- Tourne uniquement dans l'interpréteur externe (jamais dans le Python de QGIS),
  même pattern que les autres piliers lourds (`_external.run_spec`).
- 3 tests offline sur le pinning TOFU (téléchargement mocké, pas de réseau dans les
  tests) : `tests/test_geoai_segment.py`. Suite complète + ruff + mypy verts après ajout
  (140 tests).
- Doc utilisateur : `qgis_plugin/README.md` § "Use — GeoAI segmentation (experimental)".
- **Pas testé dans une vraie session QGIS** — même limite que le reste du plugin (§1 plus
  haut). Le téléchargement réel (~375 Mo) n'a pas non plus été exercé depuis cet
  environnement (réseau restreint) ; seule la logique de pinning est vérifiée par les
  tests.

### Backlog restant (pas commencé, pas prioritaire pour l'instant)
- Intégration écobuage : auto-dériver le raster critère combustible/embroussaillement
  depuis un raster brut au lieu d'exiger des rasters alignés en entrée.
- Prithvi (IBM/NASA, Apache-2.0) — cartographie post-incendie pour PAF.
- Clay Foundation Model (Apache-2.0) — alternative locale à AlphaEarth, sans compte/quota
  Earth Engine.
- Segmentation texte-guidée (Grounding DINO + SAM, Apache-2.0) — "segmente les zones
  brûlées" en langage naturel, valeur démo forte.
