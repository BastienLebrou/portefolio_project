# Packaging ScruTech pour un utilisateur tiers

Objectif : qu'une autre personne utilise ScruTech dans QGIS **sans télécharger des Go de
données** (le MNT France fait 916 Mo à lui seul). Principe : les données lourdes vivent **dans
le cloud** en formats **cloud-optimisés**, et chaque analyse ne lit **que la fenêtre de son
emprise**.

## 1. Le plugin QGIS (installable)

Le plugin se construit en ZIP : `python scrutech/vegevigie/qgis_plugin/package.py` (bundle les
moteurs), ou se déploie en dossier vif : `python scrutech/vegevigie/qgis_plugin/deploy_plugin.py`.
Pour diffuser largement : publier le ZIP + un mini `plugins.xml` (dépôt de plugins QGIS).

L'utilisateur tiers a besoin d'un interpréteur Python avec la stack (le *venv* du projet) ; le
plugin l'auto-détecte (`venv_path.txt`), sinon il le pointe dans le champ « Python executable ».

## 2. Les données lourdes : COG + GeoParquet sur R2

| Donnée | Format cloud | Lecture par l'utilisateur |
|---|---|---|
| MNT France | **COG** (GeoTIFF tuilé + aperçus) | `/vsicurl/` → seulement les tuiles de l'emprise |
| Couches BD TOPO / INPN précalculées | **GeoParquet** | lecture par plage / filtre spatial |
| Base requêtable | DuckDB | requêtes ciblées |

### Publier (côté producteur, une fois)

```bash
setx R2_ACCOUNT_ID "..."
setx R2_ACCESS_KEY_ID "..."
setx R2_SECRET_ACCESS_KEY "..."
setx R2_BUCKET "scrutech-data"

python scrutech/storage/publish_r2.py "C:/.../ressources/mnt.tif" --as mnt/france.tif --cogify
```

`publish_r2.py` convertit le MNT en COG (`core.cog.to_cog`) puis l'envoie sur R2 (API S3).
Prérequis : `pip install boto3`.

### Consommer (côté utilisateur tiers)

Il ne stocke rien : il pointe les variables sur les URL R2.

```bash
setx SCRUTECH_MNT "https://<bucket-public-ou-domaine>/mnt/france.tif"
```

`core.cog.raster_source` préfixe automatiquement les URL en `/vsicurl/`, donc écobuage et
biotrame lisent le MNT distant **sans changement de code** (seulement la fenêtre de l'emprise est
téléchargée, quelques Mo).

## 3. Ce qui reste local vs cloud

- **Cloud** : MNT (COG), couches de référence volumineuses (GeoParquet), base DuckDB.
- **Local, à la volée** : l'imagerie Sentinel-2 (déjà streamée via STAC), les réservoirs
  INPN et la BD TOPO (déjà via WFS à la demande) — rien à héberger.
- **Clé GEE** (AlphaEarth) : fournie par l'utilisateur, jamais empaquetée.

## Statut

- `core.cog` (conversion COG + lecture `/vsicurl`/`/vsis3`) : fait et testé.
- Lecture MNT distante câblée dans écobuage et biotrame : fait.
- `publish_r2.py` : prêt ; l'envoi R2 réel dépend de tes identifiants (non testable hors ligne).
- Dépôt de plugins `plugins.xml` : à générer au moment de la diffusion publique.
