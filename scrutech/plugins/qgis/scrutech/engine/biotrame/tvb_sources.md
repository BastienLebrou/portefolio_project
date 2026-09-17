# Brancher la vraie TVB régionale sur biotrame

L'axe **connectivité** de biotrame utilise, par défaut, un **proxy** (proximité aux réservoirs
Natura 2000 / ZNIEFF). Pour la remplacer par les **vrais corridors de la Trame Verte et Bleue**,
il faut un **WFS régional** — il n'existe pas de source TVB nationale unifiée (chaque DREAL
publie sa SRCE / le SRADDET publie ses corridors sur son propre serveur).

## Région Auvergne-Rhône-Alpes (Ardèche, Rhône…)

Les corridors et réservoirs de la SRCE / du SRADDET AURA sont diffusés par le **CEREMA (portail
Cartagène)** et catalogués sur **datARA** (open data public AURA) :

- Catalogue datARA (fiches SRCE, avec le lien WFS de distribution) :
  <https://catalogue.datara.gouv.fr/>
  – *« SRCE 2015 — Corridors écologiques diffus à préserver »*
  – *« SRADDET AURA — Corridors écologiques surfaciques »*
- geo.data.gouv.fr : *« SRCE — Espaces perméables terrestres de Rhône-Alpes »*
- Observatoire biodiversité AURA (GEIST) : <https://www.biodiversite-auvergne-rhone-alpes.fr/geist/>

Ouvre la fiche datARA du jeu « corridors », onglet **Diffusion / API**, et relève :
- l'**URL du service WFS** (GeoServer CEREMA/Cartagène) ;
- le **typename** de la couche corridors (ex. `ms:...corridors...`).

## Le brancher dans QGIS

Dans l'algorithme **« Priorisation écologique (biotrame, emprise seule) »**, renseigne :
- **TVB WFS URL** = l'URL WFS relevée ;
- **TVB corridor typename** = le typename de la couche corridors.

Ou, pour ne pas les retaper à chaque fois, pose-les en variables d'environnement :

```bash
setx SCRUTECH_TVB_WFS "https://<serveur-cartagene>/ows"
setx SCRUTECH_TVB_TYPENAME "<typename_corridors>"
```

Le pilier ira alors chercher les vrais corridors pour l'emprise ; le champ `connectivity_source`
du résultat passera de `reservoir_proximity_proxy` à `tvb_corridors`. En cas d'échec (serveur
indisponible, mauvais typename), il **retombe automatiquement sur le proxy** — jamais d'erreur
bloquante.

> Vérifié depuis l'implémentation : le fetch WFS générique (`core.sources.fetch_tvb_corridors`)
> fonctionne sur l'infra Géoplateforme ; l'endpoint AURA n'a pas pu être testé en direct ici
> (réseau restreint), d'où cette procédure de branchement plutôt qu'un défaut codé en dur.
