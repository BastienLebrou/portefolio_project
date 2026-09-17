<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/mantis-banner-dark.png">
  <img src="assets/mantis-banner-light.png" alt="ScruTech — voir ce que l'œil ne voit pas" width="100%">
</picture>

<br><br>

<img src="https://github.com/BastienLebrou.png?size=240" width="118" alt="Photo de profil de Bastien Lebrou">

### Bastien Lebrou

**Je fais parler les cartes.** J'analyse des territoires à partir d'images satellites et de
données publiques pour répondre à des questions concrètes.

`Portfolio géomatique & données` · `projet personnel` · `open source`

[![Mes projets](https://img.shields.io/badge/GitHub-@BastienLebrou-661C1A?logo=github&logoColor=white)](https://github.com/BastienLebrou)
[![E-mail](https://img.shields.io/badge/E--mail-me%20contacter-5C6A30?logo=maildotru&logoColor=white)](mailto:bastienlebrou1@gmail.com)
[![Ça tourne](https://github.com/BastienLebrou/portefolio_project/actions/workflows/ci.yml/badge.svg)](https://github.com/BastienLebrou/portefolio_project/actions/workflows/ci.yml)

</div>

## En deux mots

Le cartographe lit le territoire couche après couche. Mais sous ces couches, des **données
invisibles le façonnent**. **ScruTech** met la technologie au cœur du regard pour les rendre
lisibles : on lui désigne une zone sur la carte, elle va chercher la donnée toute seule
(satellite, open data), l'analyse, et rend des **cartes prêtes à décider**.

Chaque outil répond à **une question**. VegeVigie, Écobuage, Mini DC… **ne sont que des
outils** d'une seule et même plateforme.

> 🧭 Tu explores le code ? Commence par le [**guide du dépôt**](GUIDE.md) : pour chaque outil, il
> dit quel fichier ouvrir et ce qu'il fait.

## Mantis, le regard du projet

<table>
  <tr>
    <td width="34%" align="center">
      <img src="assets/mantis.png" alt="Mantis, la mascotte de ScruTech : une crevette-mante qui tient des jumelles" width="230">
    </td>
    <td>

**Mantis, la crevette-mante.** Son système visuel est le plus complexe du règne animal : seize
types de photorécepteurs (contre trois chez l'humain), l'ultraviolet, la lumière polarisée. Elle
perçoit ce que nous ne voyons pas.

C'est exactement le geste de ScruTech : révéler les **forces invisibles qui façonnent le
territoire**. Mantis est la mascotte-guide du projet — elle présente, vulgarise et relie les
outils, jumelles à la main.

  </td>
  </tr>
</table>

## Un aperçu, en images

Toutes les cartes ci-dessous sont de vraies sorties des outils, produites sur la même zone
test : 5 communes en Isère (Brézins, Plan, Saint-Étienne-de-Saint-Geoirs, Saint-Geoirs,
Saint-Pierre-de-Bressieux), environ 1 575 ha. Chaque hexagone de la carte Biotrame est une
petite zone du territoire, coloriée selon son importance pour la nature : **en bordeaux
foncé**, les 9 zones prioritaires ; **en rouge brique**, les 32 à étudier ; **en beige**, les
982 hors enjeu.

<p align="center">
  <img src="scrutech/packages/vegevigie/docs/biotrame_priority_demo.png" alt="Carte en nid d'abeilles : zones prioritaires pour la nature en Isère" width="60%">
</p>

<table>
  <tr>
    <td align="center" width="50%">
      <img src="scrutech/packages/vegevigie/docs/trend_map_demo.png" alt="Carte de la pente de Sen et des tendances significatives" width="100%"><br>
      <sub><b>La végétation pousse-t-elle ou décline-t-elle ?</b><br>41,5 % en hausse significative, 7,3 % en déclin</sub>
    </td>
    <td align="center" width="50%">
      <img src="scrutech/packages/vegevigie/docs/drought_demo.png" alt="Carte de l'anomalie et de la fréquence de stress hydrique" width="100%"><br>
      <sub><b>Où la végétation a-t-elle soif ?</b><br>Anomalie instantanée et fréquence de stress sur la période</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="scrutech/packages/vegevigie/docs/commune_ranking_demo.png" alt="Verdissement et brunissement par commune" width="100%"><br>
      <sub><b>Quelles communes surveiller ?</b><br>Part de la surface en verdissement vs en brunissement</sub>
    </td>
    <td align="center" width="50%">
      <img src="scrutech/packages/vegevigie/docs/rupture_year_demo.png" alt="Carte de l'année de rupture détectée par le test de Pettitt" width="100%"><br>
      <sub><b>Quand la tendance a-t-elle changé ?</b><br>Rupture détectée sur 55 % de la surface, surtout 2020-2023</sub>
    </td>
  </tr>
</table>

PAF trace la même logique sur un autre risque : où la forêt touche-t-elle vraiment les
habitations, là où le débroussaillement devient obligatoire.

<p align="center">
  <img src="scrutech/paff/docs/interface_demo.png" alt="Zones où la forêt touche les habitations, en rouge, sur une commune" width="60%">
</p>
<p align="center">
  <sub><b>Où la forêt touche-t-elle les habitations ?</b><br>En rouge, l'interface habitat-forêt calculée par l'outil</sub>
</p>

Écobuage répond à une question inverse : sur cette même zone, où peut-on brûler sans danger ?
La réponse est sélective — seuls 2,3 % de la surface ressortent réellement favorables.

<p align="center">
  <img src="scrutech/packages/ecobuage/docs/aptitude_demo.png" alt="Carte du score d'aptitude au brûlage dirigé et de ses classes" width="80%">
</p>

## Les outils, une question chacun

| | Outil | La question à laquelle il répond | Statut |
|:---:|---|---|:---:|
| 🌿 | **VegeVigie** | La forêt se porte-t-elle bien ? En empilant dix ans de photos satellite, l'outil repère où la végétation pousse, où elle décline, et où elle souffre de la sécheresse. | Stable |
| 🕸️ | **Biotrame** | Où concentrer les efforts pour la nature ? En croisant tous les indicateurs sur une grille, l'outil met en avant les zones prioritaires (compensation écologique). | Bêta |
| 🛰️ | **AlphaEarth** | Qu'est-ce qui a changé sur le terrain d'une année à l'autre ? On s'appuie sur des « empreintes » satellite de Google pour classer le paysage et repérer les évolutions. | Bêta |
| 🔥 | **PAF** | Où le feu menace-t-il les maisons ? L'outil trace la ligne exacte où la forêt touche les habitations, là où le débroussaillement est obligatoire. | Expérimental |
| 🌾 | **Écobuage** | Quelles parcelles peut-on brûler sans danger ? Chaque zone reçoit une note selon la végétation, la pente, l'accès et les protections en place. | Expérimental |
| 🏚️ | **SDBPi** | Quels locaux commerciaux semblent vides ? On croise les bâtiments et les entreprises actives : pas d'entreprise enregistrée à l'adresse, bâtiment à vérifier. | Expérimental |
| 🏢 | **Mini data centers** | Où installer un petit data center chez des particuliers ? On écarte les terrains impossibles, puis on note ceux qui restent. | Expérimental |
| 🌍 | **Climate Risk** | Mes fournisseurs sont-ils sur des zones déboisées ou menacées par le climat ? Un prototype de conformité (réglementation européenne EUDR). | Prototype |

*Stable : API et méthode figées. Bêta : fonctionnel, interface encore mouvante. Expérimental /
Prototype : résultats à valider avant tout usage décisionnel.*

Chaque outil a sa propre page détaillée : [VegeVigie](scrutech/packages/vegevigie/) ·
[Biotrame](scrutech/packages/biotrame/) · [AlphaEarth](scrutech/packages/alphaearth/) · [PAF](scrutech/docs/paf/) ·
[Écobuage](scrutech/packages/ecobuage/) · [SDBPi](scrutech/applications/sdbpi/) ·
[Mini data centers](scrutech/applications/mini-data-centers/) · [Climate Risk](scrutech/applications/climate-risk-analyzer/).

## Comment ça marche

Toujours le même principe, quel que soit l'outil : on part d'une zone, on finit avec des cartes.

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#F1E8D2','primaryBorderColor':'#661C1A','primaryTextColor':'#2B261D','lineColor':'#5C6A30','fontFamily':'IBM Plex Sans, Segoe UI, sans-serif'}}}%%
flowchart LR
    A["🗺️ Une zone<br/>sur la carte"] --> B["📡 L'outil va chercher<br/>la donnée tout seul<br/>(satellite, open data)"]
    B --> C["⚙️ Il analyse<br/>et croise"]
    C --> D["🗂️ Des cartes prêtes<br/>à ouvrir dans QGIS"]
```

Et tout se lance aussi **en un clic** depuis QGIS, le logiciel de cartographie que connaissent
les géomaticiens, grâce à une extension dédiée.

<details>
<summary><b>🔧 Pour les curieux : sous le capot</b></summary>

<br>

Rien n'est bricolé à la main : chaque analyse est un **programme reproductible**, testé, qu'on
peut relancer à l'identique. Les grands blocs techniques :

| Domaine | Outils employés |
|---|---|
| Images satellites & séries temporelles | Sentinel-2, STAC, xarray / dask, rasterio |
| Traitement de données géo | GeoPandas, Shapely, PostGIS, DuckDB spatial, GeoParquet |
| Statistiques de tendance | Mann-Kendall, pente de Sen, Pettitt, VCI |
| Analyse multicritère & maillage | scoring pondéré, grille hexagonale H3, connectivité |
| Restitution | extension QGIS, cartes, tableaux de bord, tuiles web |
| Qualité du code | plus de 150 tests automatisés, intégration continue, typage |

Le tout repose sur un **socle commun** (`core`) : une zone en entrée, et tout le reste en
découle (lecture / écriture des données, base spatiale, rangement des résultats). Pour trouver
n'importe quel script, voir le [**guide du dépôt**](GUIDE.md) ; la
[politique de sécurité](SECURITY.md) complète le tableau.

</details>

## Un test grandeur nature, en chiffres

Résultats d'un vrai passage de la chaîne complète sur une zone test de 5 communes en Isère
(Brézins, Plan, Saint-Étienne-de-Saint-Geoirs, Saint-Geoirs, Saint-Pierre-de-Bressieux —
environ 1 575 ha). Pas une simulation : ce sont les couches produites par les outils sur cette
zone.

| Outil | Ce qui a été mesuré |
|---|---|
| 🌿 **VegeVigie** | Sur les 1 575 ha : **41,5 % en hausse significative** de NDVI, **7,3 % en déclin significatif**, le reste sans tendance nette. Une rupture statistique (test de Pettitt) est détectée sur **54,9 % de la surface**, très majoritairement en **2020, 2021 et 2023** — les années de sécheresse marquée dans la région. **25 % de la surface (397 ha)** reste durablement au-dessus du seuil de stress hydrique. |
| 🕸️ **Biotrame** | Sur 1 023 hexagones (1 477 ha), seuls **9 hexagones (13 ha, 0,9 %)** ressortent en priorité maximale pour la compensation écologique, et **32 (46 ha, 3,1 %)** en priorité moyenne — le reste hors enjeu prioritaire. Une vraie sélection, pas une carte où tout est rouge. |
| 🔥 **PAF** | **47,6 km** d'interface habitat-forêt identifiés sur la zone, soit **49 ha** de bande à débroussailler obligatoirement. |
| 🌾 **Écobuage** | Aptitude moyenne **15,7/100** : seuls **5,9 % de la surface (93 ha)** dépassent le seuil favorable. Le détail par classe : 76,9 % exclu, 20,8 % moyen, **2,3 % (36 ha) réellement favorable au brûlage**. |

Le classement par commune (VegeVigie) montre des écarts nets : Plan ressort avec **64 % de
sa surface en verdissement** et l'anomalie moyenne la plus forte, contre 35 % pour Brézins ou
Saint-Pierre-de-Bressieux.

<sub>Zone de démonstration, pas un échantillon représentatif du territoire national — les
seuils (favorable/prioritaire/stress) sont ceux configurés par défaut dans chaque outil.</sub>

## Le projet en chiffres

Ces chiffres se mettent à jour **tout seuls, tous les deux jours**, à partir de l'historique réel
du projet.

<!-- AUTO-STATS:START -->
| 📦 Commits | 📅 Jours actifs | 🗂️ Projets |
|:---:|:---:|:---:|
| **121** | **44** | **1** |

| 🐍 Lignes de Python | ✅ Tests automatisés | 🥇 Langage principal |
|:---:|:---:|:---:|
| **18 325** | **179** | **Python (80,4 %)** |

*Dernière mise à jour automatique : 17 septembre 2026 à 14:04 (heure de Paris) — commit `ff89a96`.*
<!-- AUTO-STATS:END -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/activity-dark.svg">
  <img src="assets/activity-light.svg" alt="Activité du projet, semaine par semaine" width="100%">
</picture>

<details>
<summary>Voir la répartition des langages et des jours de travail</summary>

<table>
  <tr>
    <td width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="assets/languages-dark.svg">
        <img src="assets/languages-light.svg" alt="Répartition des langages du projet" width="100%">
      </picture>
    </td>
    <td width="50%">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="assets/weekdays-dark.svg">
        <img src="assets/weekdays-light.svg" alt="Répartition des commits par jour de la semaine" width="100%">
      </picture>
    </td>
  </tr>
</table>

</details>

## Me contacter

Je cherche un poste de **géomaticien** (Métropole de Lyon ou en télétravail). Discutons-en.

- GitHub : [@BastienLebrou](https://github.com/BastienLebrou)
- E-mail : [bastienlebrou1@gmail.com](mailto:bastienlebrou1@gmail.com)

<sub>Mantis et l'identité visuelle sont maison. Les chiffres et graphiques sont calculés depuis
l'historique réel du projet — rien n'est saisi à la main.</sub>
