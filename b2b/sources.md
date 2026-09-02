# Journal des sources — audit B2B du 2026-09-02

Toutes les sources ci-dessous ont été consultées le **2026-09-02** depuis l'environnement
d'audit. Statut : `vérifié` = page lue ou résumé de recherche exploitable ; `à vérifier` =
la page n'a pas pu être ouverte, l'information reste à confirmer avant tout engagement.

## A. Sources internes (dépôt)

| Fait retenu | Fichier |
|---|---|
| Scope, stack figée, jalons, objectif plugin QGIS | `scrutech/vegevigie/CLAUDE.md` |
| Statut réel de VegeVigie (figures synthétiques, egress STAC bloqué) | `scrutech/vegevigie/README.md` §Status & limitations |
| Résultats réels SDBPi (Bourg-en-Bresse, Grand Lyon) + sensibilité au buffer | `scrutech/sdbpi/README.md` |
| Plafonds d'API et contournements (WFS 5000, SIRENE 10000, per_page 25) | `scrutech/sdbpi/README.md`, `scrutech/sdbpi/sources.py`, `scrutech/core/src/core/sources.py` |
| WUI : géométrie, exports, CRS métrique | `scrutech/vegevigie/src/vegevigie/interface.py`, `tests/test_interface.py` |
| Statut PAF (segmentation priorisée non faite) | `scrutech/paff/README.md` §Statut |
| mini_dc : entonnoir, H3, couche QA, invariants SQL | `scrutech/mini_dc/outil/{pipeline,tests_pipeline}.py`, `outil/GUIDE_CONTROLE_SIG.md` |
| mini_dc : ABF et PPRI absents du run réel | `scrutech/mini_dc/outil/analyse_reelle.py` (docstring) |
| Écobuage : livrable final en attente d'une emprise réelle | `scrutech/ecobuage/README.md` |
| Biotrame : axe connectivité en proxy, endpoint AURA non testé | `scrutech/biotrame/TVB_SOURCES.md` |
| AlphaEarth : tests mockés, pas de requête GEE réelle | `scrutech/alphaearth/tests/test_client.py`, `alphaearth/README.md` |
| Climate Risk : scores mock, v0.1.0 experimental | `scrutech/climate_risk_analyzer/README.md` |
| Plugin hub : 14 algorithmes, jamais lancé en QGIS live | `qgis_plugin/scrutech/metadata.txt`, `vegevigie/CLAUDE.md` §11 |
| Store DuckDB central, layout `aoi=…/produit/`, S3 non implémenté | `scrutech/storage/schema.sql`, `core/src/core/storage.py` |
| CI multi-paquets (3 sessions pytest) | `.github/workflows/ci.yml` |
| Absence de PostGIS / Docker / S3 dans le code | greps : `postgis` (2 commentaires), `*docker*` (0), `boto3\|s3://` (0) |
| Vault `claude_vault` introuvable | `find / -iname "*claude_vault*"` → 0 résultat |

## B. Sources externes (signaux de demande)

| # | Requête / sujet | Lien | Fait daté retenu | Statut |
|---|---|---|---|---|
| 1 | EUDR, calendrier d'application | <https://trade.ec.europa.eu/access-to-markets/en/news/delay-until-december-2026-and-other-developments-implementation-eudr-regulation> | Application 30/12/2026 (grandes et moyennes entreprises), 30/12/2027 (micro/petits) ; simplification (~-30 % de charge administrative) | vérifié |
| 2 | OLD, loi 2023-580 et décrets | <https://blog.landot-avocats.net/2024/04/01/obligations-legales-de-debroussaillement-old-et-autres-regles-de-lutte-contre-le-risque-dincendie-deux-nouveaux-decrets/> · <https://www.ernmt-officiel.com/blog/article/obligation-legal-debroussaillement> | Loi du 10/07/2023 ; décret n° 2024-284 du 29/03/2024 ; information OLD obligatoire dans l'état des risques depuis le 01/01/2025 | vérifié (relais — texte officiel à relire sur Légifrance) |
| 3 | Sinistralité climatique et feux | <https://www.franceassureurs.fr/wp-content/uploads/2022/09/vf_france-assureurs_impact-du-changement-climatique-2050.pdf> · <https://www.argusdelassurance.com/environnement/risques-climatiques/incendies-de-vegetation-face-a-un-risque-appele-a-gagner-la-moitie-de-la-france-la-prevention-devient-un-enjeu-majeur-pour-lassurance.PH4SJRUZU5ABTAC2Y4OVUXNB6Y.html> | 73,4 → 143 Md€ de sinistres (2020→2050) ; +~70 % de jours à risque élevé d'incendie d'ici 2050 (étude AXA Climate) ; l'assurance forêt s'est retirée de certaines zones méditerranéennes | vérifié |
| 4 | RGA — coût et exposition | <https://www.senat.fr/rap/r23-603/r23-603_mono.html> · <https://www.economie.gouv.fr/actualites/rapport-mieux-assurer-francais-changement-climatique> | 400 M€/an (1989-2015) → ~1 Md€/an (2016-2020) → 3,5 Md€ en 2022 ; 55 % du territoire en exposition moyenne/forte ; surprime CatNat 12 % → 20 % au 01/01/2025 ; rapport Langreney remis le 02/04/2024 | vérifié |
| 5 | Agrivoltaïsme — zone témoin et contrôle | <https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000049386027> | Décret n° 2024-318 du 08/04/2024 : zone témoin ≥ 5 % (max 1 ha), rendement ≥ 90 % de la zone témoin ; arrêté du 05/07/2024 : rapport avant mise en service + contrôle à 6 ans | vérifié |
| 6 | Gestion de la végétation réseaux | <https://www.marchesonline.com/appels-offres/avis/gestion-de-la-vegetation-lot-1-solution-modulaire-d/ao-9501043-1> · <https://www.rte-france.com/synthese-guide-pratique-vegetation-abords-lignes-electriques> | Appel d'offres Enedis « Gestion de la végétation — Lot 1 » (traitement de données LIDAR/imagerie/satellite, identification des zones à risque) | **à vérifier** — domaine bloqué par le proxy d'egress ; date, montant et acheteur non documentés |
| 7 | Data centers — raccordement | <https://www.rte-france.com/bases-electricite/consommation-electricite/essor-data-centers-france> · <https://www.usinenouvelle.com/eco-social/economie/usines-de-batteries-data-centers-sites-chimiques-ou-en-sont-les-projets-industriels-choose-france.L6CL7C4U4NHRLIVGLOLDDSM4BE.html> | Mai 2026 : ~18 GW réservés pour ~80 projets (vs ~5 GW / ~40 projets fin 2024) ; fast track pour 5 sites de 700 MW-1 GW ; 63 sites « clés en main », 26 localisations publiques en août 2026 | vérifié |
| 8 | Inventaire ZAE et taux de vacance | <https://www.legifrance.gouv.fr/jorf/article_jo/JORFARTI000043957249> · <https://www.paca.developpement-durable.gouv.fr/loi-climat-resilience-foire-aux-questions-zae-a14744.html> | Art. 220 de la loi n° 2021-1104 du 22/08/2021 : état parcellaire, occupants, **taux de vacance** (non utilisé depuis ≥ 2 ans) ; première échéance 24/08/2023 ; finalité = recyclage foncier | vérifié |
| 9 | SNCRR — cadre réglementaire | <https://www.banquedesterritoires.fr/sites-naturels-de-compensation-de-restauration-et-de-renaturation-le-cadre-reglementaire-est-fixe> | Loi n° 2023-973 du 23/10/2023 (industrie verte) ; décrets n° 2024-1052 et 2024-1053 + arrêté du 21/11/2024 publiés le 23/11/2024 (agrément et suivi, instruction DREAL, avis CSRPN) | vérifié |
| 10 | CSRD / ESRS E4 post-omnibus | <https://www.coolset.com/academy/esrs-e4-biodiversity-and-ecosystems> | Périmètre post-omnibus : > 1 000 salariés ou 450 M€ de CA ; E4 applicable si matériel ; calendrier décalé (vague 2 en 2028) | vérifié (relais — **à recouper avec le texte officiel**) |
| 11 | Label bas-carbone (piste connexe non retenue) | <https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000052201236> | Décret n° 2025-917 et arrêté du 05/09/2025 : nouveau référentiel, traçabilité et déclaration obligatoire des financements ; cadre européen de certification carbone forêt attendu en 2028 | vérifié |

## Sources demandées mais indisponibles

| Source | Motif |
|---|---|
| Vault Obsidian `claude_vault` | Absent du système de fichiers de la session (aucun résultat, aucun dossier `.obsidian`) |
| Fichiers de mémoire projet Claude | Aucun fichier de mémoire `.md` dans `~/.claude/projects/-home-user-portefolio-project/` |
| `CLAUDE.md` racine | N'existe pas — seul `scrutech/vegevigie/CLAUDE.md` est présent |
| Dépôts ScruTech séparés | Le code est un monorepo sous `scrutech/` ; il n'y a pas de dépôts VegeVigie / PAF / mini_dc distincts |
| Fiche de l'appel d'offres Enedis | Domaine `marchesonline.com` bloqué par le proxy d'egress |
