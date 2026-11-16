"""Markdown report of the environmental data diagnostic (French, ecologist-style).

Pure text assembly from the DataFrames the other modules produce: no network, no plotting. The
PDF (:mod:`biodiag.pdf`) renders this same Markdown, so the two never disagree.

Style rule: short plain sentences, no bold, no bullet lists, no filler dashes. Data goes in
tables, explanations in short paragraphs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from biodiag.gbif import RECENT_FROM

EFFET = {
    "Forte": "Perte d'habitat de reproduction ou d'alimentation en milieu ouvert. Risque d'évitement du parc.",
    "Modérée": "Perte partielle d'habitat et dérangement en travaux. Recolonisation possible selon la gestion.",
    "Faible": "Peu d'effet en exploitation. Risque surtout en travaux (mortalité, dérangement).",
}

GLOSSARY = [
    ("ZIP", "Zone d'implantation potentielle : les parcelles du projet."),
    ("ZER, ZEE", "Zones d'étude rapprochée (1 km autour des parcelles) et éloignée (5 km)."),
    ("GBIF", "Base mondiale ouverte d'observations d'espèces, alimentée par des naturalistes, des associations et des programmes de suivi."),
    ("INPN", "Inventaire national du patrimoine naturel, qui diffuse les zonages de protection et d'inventaire."),
    ("ZNIEFF", "Zone naturelle d'intérêt écologique, faunistique et floristique. Le type I est un secteur restreint de grand intérêt, le type II un grand ensemble naturel. C'est un inventaire, sans portée réglementaire directe."),
    ("Natura 2000", "Réseau européen de sites protégés. Les ZSC protègent habitats et espèces de la directive Habitats, les ZPS les oiseaux de la directive Oiseaux."),
    ("PNA", "Plan national d'actions en faveur d'une espèce menacée."),
    ("DO, DHFF", "Directive Oiseaux et directive Habitats-Faune-Flore. Leurs annexes listent les espèces à protéger."),
    ("UICN", "Union internationale pour la conservation de la nature. Catégories de la liste rouge : CR en danger critique, EN en danger, VU vulnérable, NT quasi menacée, LC préoccupation mineure, NE non évaluée."),
    ("Espèce patrimoniale", "Dans ce dossier, espèce protégée inscrite à une directive européenne, menacée, quasi menacée ou citée dans une liste locale. La protection nationale seule ne suffit pas."),
    ("Enjeu fort, modéré, faible", "Niveau d'attention donné à une observation. Fort : espèce patrimoniale signalée en ZER ou dans un zonage fort. Ce classement tient compte de la position seule : il ne dit pas que l'espèce utilise les parcelles. Modéré : espèce patrimoniale plus loin, ou espèce protégée commune en ZER. Faible : le reste."),
    ("Observation imprécise", "Observation dont la position est connue à plus de 1 km près. Elle est placée au centre d'une maille d'environ 5 km."),
    ("EEE", "Espèce exotique envahissante."),
    ("ERC", "Éviter, réduire, compenser : démarche qui encadre les impacts d'un projet sur la nature."),
]  # fmt: skip


@dataclass
class Case:
    """Everything the report needs, gathered by :mod:`biodiag.biodiag_aoi`."""

    title: str
    area_ha: float
    centroid: tuple[float, float]
    zer_m: int
    zee_m: int
    zer_km2: float
    zee_km2: float
    rpg: list[str]
    habitat: str
    synthese: pd.DataFrame
    pressure: dict
    context: dict
    pna: pd.DataFrame
    protected: pd.DataFrame
    incidences: pd.DataFrame
    env: dict
    counts: dict
    meta: dict
    sp_band: pd.DataFrame
    obs_band: pd.DataFrame
    pat_band: pd.DataFrame
    justif: pd.DataFrame
    justif_far: pd.DataFrame
    flora: dict
    motorway: dict
    habitats: pd.DataFrame
    hab_facts: dict
    coarse: pd.DataFrame
    coarse_info: dict
    bats: pd.DataFrame
    odonata: dict
    n2k: list
    annex_a: pd.DataFrame
    coarse_table: pd.DataFrame
    project: dict = field(default_factory=dict)
    ref: str = ""
    intro: str = ""
    control: str = ""
    figures: dict[str, str] = field(default_factory=dict)
    images: dict[str, str] = field(default_factory=dict)
    n_patri_zip: int = 0
    bias: dict = field(default_factory=dict)


def fr(x: float, nd: int = 1) -> str:
    """Number with a French decimal comma."""
    return f"{x:.{nd}f}".replace(".", ",")


def nb(n: float) -> str:
    """Integer with thin-space thousands separator."""
    return f"{int(round(n)):,}".replace(",", " ")


def tab(df: pd.DataFrame) -> str:
    """DataFrame -> Markdown table (empty frame -> an explicit "none")."""
    if df is None or df.empty:
        return "Aucune donnée.\n"
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    rows = "\n".join(
        "| " + " | ".join(str(v).replace("|", "/") for v in r) + " |" for r in df.values
    )
    return head + rows + "\n"


def build(c: Case) -> str:
    ctx, cn, pj = c.context, c.counts, c.project
    ha = c.area_ha
    patri = c.synthese[c.synthese.Enjeu == "Fort"]
    n_patri_zer = int((patri["Nb obs ZIP/ZER"] > 0).sum())
    pp = c.pressure
    sp = c.sp_band
    tot = sp.loc["Toutes espèces"]
    a_min, a_max = cn.get("from_year", cn.get("annee_min", "")), cn.get("annee_max", "")
    ann = c.meta.get("annoncees", cn["telecharge"])
    d_a9 = c.env.get("autoroute_dist")
    eau = c.env["eau"]
    hydro = c.env["hydro"]
    basin = (
        hydro[hydro.nature.str.contains("bassin", case=False, na=False)] if len(hydro) else hydro
    )
    d_basin = float(basin.d.min()) if len(basin) else None
    hab = c.habitat or "occupation du sol à vérifier sur orthophoto"
    fl = c.flora
    ci = c.coarse_info
    z1 = ctx["cov_zer"]
    d_fort = ctx["d_fort"]
    zsc = next((s for s in c.n2k if s["type"] == "ZSC"), None)
    ref = f" ({c.ref})" if c.ref else ""
    imgs = c.images
    figs = c.figures

    def img(key: str, caption: str) -> str:
        path = imgs.get(key)
        return f"![{caption}]({path})\n" if path else ""

    def fig(prefix: str, caption: str) -> str:
        path = next((p for stem, p in sorted(figs.items()) if stem.startswith(prefix)), None)
        return f"![{caption}]({path})\n" if path else ""

    pv = c.env["pv"]
    pv_t = (
        pv.assign(S=(pv.surf_parc / 1e4).round(1), D=(pv.d / 1000).round(2))[
            ["commune", "millesime", "S", "D"]
        ].rename(
            columns={
                "commune": "Commune",
                "millesime": "Millésime",
                "S": "Surface (ha)",
                "D": "Distance (km)",
            }
        )
        if len(pv)
        else pd.DataFrame()
    )
    if len(pv_t):
        pv_t["Surface (ha)"] = pv_t["Surface (ha)"].map(lambda v: fr(v, 1))
        pv_t["Distance (km)"] = pv_t["Distance (km)"].map(lambda v: fr(v, 2))
    wind = c.env.get("wind", pd.DataFrame())
    wind_t = (
        wind.assign(D=(wind.d / 1000).map(lambda v: fr(v, 2))).rename(
            columns={"commune": "Commune", "annee": "Année", "n": "Éoliennes", "D": "Distance (km)"}
        )[["Commune", "Année", "Éoliennes", "Distance (km)"]]
        if len(wind)
        else pd.DataFrame()
    )
    resp = pd.DataFrame(
        [
            [
                "Relever les données GBIF",
                f"Toutes les données de {a_min} à {a_max} sur 5 km, comptes exacts par distance",
                "Chapitres 3 et 5, annexes A et B",
            ],
            [
                "Espèces des sites Natura 2000 (DOCOB)",
                "Objectifs des sites, espèces communes avec le secteur, raisons de l'absence de lien",
                "Chapitre 6",
            ],
            [
                "Espèces protégées recensées",
                "Une raison d'absence d'impact pour chaque espèce patrimoniale",
                "Chapitre 5.2",
            ],
            [
                "Plans nationaux d'actions",
                "Présence par espèce et lecture favorable au projet",
                "Chapitre 5.8",
            ],
            [
                "Mesures de réduction",
                "Calendrier (pas de travaux d'avril à juillet), passage d'un écologue avant le chantier, éclairage, clôture, passages, invasives",
                "Chapitre 8",
            ],
            [
                "Cours d'eau proche, attractivité des panneaux",
                "Panneaux inclinés à 15°, donc non horizontaux, disposés en rangées discontinues séparées par des inter-rangs enherbés. La surface n'est ni horizontale ni continue : elle ne peut pas être confondue avec une étendue d'eau par les insectes aquatiques, les oiseaux d'eau ou les chauves-souris.",
                "Chapitres 4.3 et 7.2",
            ],
            [
                "Espèces exotiques envahissantes",
                "Nettoyage des engins et entretien régulier",
                "Chapitres 7.3 et 8",
            ],
            [
                "Effets cumulés",
                "Parcs photovoltaïques et éoliens recensés dans les 5 km",
                "Chapitre 10",
            ],
            ["Suivi", "Contrôle annuel des clôtures, des haies et des invasives", "Chapitre 8"],
            [
                "Choix de la zone d'implantation",
                "Zone hors zonage environnemental et patrimonial, en milieu déjà anthropisé",
                "Chapitre 2",
            ],
        ],
        columns=["Demande de l'avis", "Réponse du dossier", "Où"],
    )
    reptiles = (
        int(c.obs_band.loc["Reptiles"].iloc[:4].sum()) if "Reptiles" in c.obs_band.index else 0
    )
    rept_txt = (
        "Aucune observation de reptile n'existe à moins de 2 km dans les données précises."
        if reptiles == 0
        else f"{reptiles} observations de reptiles existent à moins de 2 km dans les données précises."
    )
    intro = f"{c.intro}\n\n" if c.intro else ""
    control = f"{c.control}\n\n" if c.control else ""
    veg_ouvert = c.hab_facts["open_ha"]
    bats_n = c.bats.Espèce.nunique() if len(c.bats) else 0
    bi = c.bias
    near = c.pat_band[c.pat_band["Distance min. (m)"] <= 1000]
    near_counts = near[["0 à 500 m", "500 m à 1 km"]].sum(axis=1)
    near_min = int(near_counts.min()) if len(near_counts) else 0
    near_max = int(near_counts.max()) if len(near_counts) else 0
    bats_obs = int(c.bats["Relevés"].sum()) if len(c.bats) else 0
    hab_t = c.habitats.copy()
    if len(hab_t):
        hab_t["Surface en ZER (ha)"] = hab_t["Surface en ZER (ha)"].map(lambda v: fr(v, 1))
    zn = c.protected[c.protected.Zonage == "ZNIEFF I"] if len(c.protected) else c.protected
    zn_dist_col = "Distance à l'emprise"
    znieff_txt = (
        f"Le ZNIEFF de type I le plus proche, « {zn.iloc[0]['Nom']} », est à {zn.iloc[0][zn_dist_col]}."
        if len(zn)
        else ""
    )
    flora_zer_txt = (
        "Aucune de ces espèces n'est protégée ni patrimoniale."
        if not (fl["protegee_zer"] or fl["patrimoniale_zer"])
        else "Parmi elles, "
        + ", ".join(sorted(set(fl["protegee_zer"]) | set(fl["patrimoniale_zer"])))
        + " sont protégées ou patrimoniales."
    )
    fp = fl["patrimoniale_zee"]
    flora_pat_txt = (
        "Les espèces de flore patrimoniales de la zone éloignée sont "
        + (", ".join(fp[:-1]) + " et " + fp[-1] if len(fp) > 1 else fp[0])
        + f". La plus proche est à {nb(min(fl['dist_patri_min'].values()))} m."
        if fp
        else "Aucune espèce de flore patrimoniale n'est signalée dans la zone éloignée."
    )
    top3 = list(c.bats.Espèce.head(3)) if len(c.bats) else []
    bats_dom = (
        "Les pipistrelles dominent : ce sont des espèces courantes autour des habitations et des routes."
        if top3 and all(s.startswith(("Pipistrellus", "Hypsugo")) for s in top3)
        else ""
    )
    lz = c.pat_band[c.pat_band.Espèce.str.startswith("Timon lepidus")]
    pna0 = c.pna.iloc[0]
    lezard_txt = (
        f"Le Lézard ocellé, cité par l'avis, n'est signalé que dans la zone éloignée : {pna0['Obs. ZEE']} observations dans les 5 km, "
        f"la plus proche à {nb(lz.iloc[0]['Distance min. (m)'])} m, la dernière en {pna0['Dernière année']}."
        if len(lz) and pna0["Obs. ZEE"]
        else "Le Lézard ocellé, cité par l'avis, n'est pas signalé près des parcelles."
    )

    resume = pd.DataFrame(
        [
            ["Surface des parcelles", f"{fr(ha, 2)} ha"],
            ["Période des données", f"{a_min} à {a_max}"],
            ["Observations téléchargées", nb(cn["telecharge"])],
            ["Observations précises retenues", nb(cn["retenues"])],
            ["Observations sur les parcelles", "0"],
            ["Espèces à moins de 500 m", nb(tot["0 à 500 m"])],
            ["Espèces entre 500 m et 1 km", nb(tot["500 m à 1 km"])],
            ["Espèces patrimoniales à moins de 1 km", f"{n_patri_zer}"],
            [
                "Flore protégée ou patrimoniale à moins de 1 km",
                f"{len(fl['protegee_zer']) + len(fl['patrimoniale_zer'])}",
            ],
            [
                "Site Natura 2000 le plus proche",
                f"ZSC à {fr(zsc['dist_km'], 2)} km" if zsc else "aucun",
            ],
            ["ZNIEFF de type I la plus proche", f"{fr(d_fort / 1000, 2)} km" if d_fort else "n.c."],
            ["Distance à l'autoroute A9", f"{fr(d_a9, 0)} m" if d_a9 is not None else "n.c."],
        ],
        columns=["Donnée", "Valeur"],
    )

    toc = [
        "1. Synthèse",
        "2. Choix de la zone d'implantation",
        "3. Méthode et traitement des données",
        "4. Habitats",
        "5. Espèces",
        "6. Zonages et réglementation",
        "7. Incidences du projet",
        "8. Mesures d'évitement et de réduction",
        "9. Réponse point par point à l'avis de la DDTM",
        "10. Effets cumulés",
        "11. Conclusion",
        "12. Limites",
    ]
    P = [
        f"# Diagnostic par analyse de données environnementales : {c.title}\n\nGénéré le {time.strftime('%d/%m/%Y')}.\n"
    ]
    P.append("## Table des matières\n\nGlossaire\n\n" + "\n\n".join(toc) + "\n")
    P.append("## Glossaire\n\n" + tab(pd.DataFrame(GLOSSARY, columns=["Terme", "Définition"])))

    # ------------------------------------------------------------------ 1
    P.append(
        f"""## 1. Synthèse

{intro}Ce dossier relève l'ensemble des données GBIF disponibles autour du projet de centrale photovoltaïque au sol{ref}, de {a_min} à {a_max}, dans un rayon de 5 km. Il les croise avec les zonages de protection de l'INPN.

{control}{tab(resume)}
Aucune observation n'existe sur les parcelles elles-mêmes. À moins de 1 km, {n_patri_zer} espèces patrimoniales sont signalées, chacune par {near_min} à {near_max} observations. Elles sont classées en enjeu fort sur le seul critère de la position, par prudence. Aucune ne dépend des parcelles : chaque cas est détaillé au chapitre 5 et en annexe B.

Les parcelles sont hors ZNIEFF et hors site Natura 2000. Le site Natura 2000 le plus proche est à {fr(zsc["dist_km"], 2) if zsc else "n.c."} km. L'autoroute A9 borde les parcelles à {fr(d_a9 or 0, 0)} m.

Le projet ne remanie le sol que pour la voie d'accès pompier (moins de 400 m²), ne prévoit pas de chantier lourd (travaux limités en durée et en emprise, pas de travaux d'avril à juillet, passage d'un écologue avant le démarrage), n'utilise pas de produit phytosanitaire et conserve la végétation par une fauche annuelle tardive. Les données historiques ne montrent aucun élément concret qui empêche son développement.
"""
    )

    # ------------------------------------------------------------------ 2 (zone choice)
    P.append(
        f"""## 2. Choix de la zone d'implantation

Les parcelles sont intégrées au document cadre photovoltaïque de l'Aude. Elles se situent en dehors de tout zonage environnemental (ZNIEFF, Natura 2000, APPB, réserves), dans un milieu déjà anthropisé par l'autoroute A9 ({fr(d_a9 or 0, 0)} m) et son aire de repos. Le site est à l'écart du village de Bizanet (premières maisons du village à plus de 1,5 km) et de toute habitation (habitation isolée la plus proche à plus de 500 m). Il est également en dehors de tout zonage patrimonial, sans visibilité ni covisibilité depuis un monument historique, un site classé ou inscrit, ou un bien inscrit au patrimoine mondial de l'UNESCO.
"""
    )

    # ------------------------------------------------------------------ 3
    P.append(
        f"""## 3. Méthode et traitement des données

Toutes les observations publiées sur GBIF dans un rayon de 5 km autour des parcelles ont été téléchargées, quelle que soit leur date. Seules celles de {
            cn["from_year"]
        } et après sont analysées : les {
            nb(cn["avant_periode"])
        } observations plus anciennes sont trop rares pour décrire l'état actuel du secteur. La période analysée va de {
            a_min
        } à {
            a_max
        }. Le téléchargement est découpé par année, par jeu de données et par mois, pour ne perdre aucune observation. GBIF annonce {
            nb(ann)
        } observations. {nb(cn["telecharge"])} ont été téléchargées et {
            c.meta.get("pages_perdues", 0)
        } page a été perdue.

{img("schema", "Schéma de traitement des données")}
Cinq contrôles sont appliqués. Le tableau donne le nombre d'observations à chaque étape.

{
            tab(
                pd.DataFrame(
                    [
                        [
                            "Observations téléchargées",
                            nb(cn["telecharge"]),
                            "Rayon de 5 km, toutes années",
                        ],
                        [
                            "Sans nom d'espèce",
                            nb(cn["avec_coordonnees"] - cn["rang_espece"]),
                            "Écartées : déterminées au genre ou à la famille",
                        ],
                        [
                            "Position imprécise (plus de 1 km)",
                            nb(cn["imprecis"]),
                            "Analysées à part, annexe B",
                        ],
                        ["Doublons", nb(cn["doublons"]), "Écartés (même espèce, lieu et date)"],
                        [
                            f"Antérieures à {cn['from_year']}",
                            nb(cn["avant_periode"]),
                            "Écartées : anciennes et rares",
                        ],
                        [
                            "Observations précises retenues",
                            nb(cn["retenues"]),
                            f"Dont {nb(cn['historiques'])} d'avant {RECENT_FROM}, gardées et signalées",
                        ],
                    ],
                    columns=["Étape", "Observations", "Traitement"],
                )
            )
        }
Les observations imprécises représentent la majorité du jeu : {
            nb(cn["imprecis"])
        } observations. Après regroupement des relevés identiques (même espèce, même lieu, même date), il reste {
            nb(ci["n_obs"])
        } relevés pour {
            nb(ci["n_species"])
        } espèces. Leur position est celle du centre d'une maille d'environ 5 km, avec une précision médiane de {
            nb(ci["median_u"])
        } m. Elles disent qu'une espèce a été vue dans le secteur, pas sur les parcelles. Elles ne servent donc pas à classer les enjeux, mais elles ont été analysées une à une (annexe B). Elles ajoutent {
            ci["n_patri_new"]
        } espèces patrimoniales absentes du jeu précis. Parmi elles, {
            bats_n
        } espèces de chauves-souris, issues surtout du suivi acoustique de parcs éoliens voisins.

### Biais d'observation

Les données GBIF viennent d'observateurs : leur répartition n'est pas homogène. Autour des parcelles, {
            nb(bi["n_150"] / bi["n_near"] * 100)
        } % des observations à moins de 500 m sont à moins de 150 m de l'A9 ou d'une aire de repos, et un seul observateur fournit {
            nb(bi["n_top"] / bi["n_near"] * 100)
        } % d'entre elles. Sans lui, le nombre d'espèces à moins de 500 m passe de {
            nb(bi["sp_near"])
        } à {nb(bi["sp_without"])}, et les {
            nb(bi["patri_all"])
        } espèces patrimoniales à moins de 1 km restent les mêmes. Le jeu de données donne donc une image, même imprécise, des espèces présentes dans le secteur. Il ne mesure pas l'usage des parcelles elles-mêmes : l'absence d'observation sur les parcelles tient à l'absence d'observateurs et ne prouve pas l'absence d'espèces.

{img("biais", "Carte du biais d'observation")}
{fig("fig_9", "Densité d'observations selon la distance à l'autoroute")}
Les parcelles couvrent {fr(ha / c.hab_facts["zer_ha"] * 100, 2)} % de la zone rapprochée et {
            fr(ha / (c.zee_km2 * 100) * 100, 3)
        } % de la zone éloignée. Les milieux voisins, d'où viennent les observations, ne sont pas touchés. Le projet ne remanie le sol que pour la voie d'accès pompier et conserve la végétation basse. Le changement d'usage porte donc sur une surface très petite et ne devrait pas modifier de façon importante l'environnement observé.

Pression d'inventaire. La zone rapprochée compte {nb(pp["n_zer"])} observations ({
            nb(pp["par_km2"])
        } par km²) pour {
            nb(pp["n_esp_zer"])
        } espèces. La flore y est inventoriée par le conservatoire botanique : {
            nb(fl["n_obs_zee"])
        } observations de flore dans les 5 km.

{fig("fig_7", "Observations GBIF par année")}
"""
    )

    # ------------------------------------------------------------------ 3
    P.append(
        f"""## 4. Habitats

### 4.1 Les parcelles

Les parcelles couvrent {fr(ha, 2)} ha. Occupation du sol d'après l'orthophoto : {hab}. L'autoroute A9 les borde à {fr(d_a9 or 0, 0)} m. Elle longe le sud-ouest des parcelles et en constitue la limite physique : elle les sépare des milieux situés de l'autre côté de la chaussée.

{pj.get("sol_txt", "")}

{img("proximite", "Carte de proximité")}
### 4.2 Habitats similaires à proximité

La zone rapprochée couvre {nb(c.hab_facts["zer_ha"])} ha. Les milieux ouverts de la zone rapprochée (vignes, vergers, landes) occupent environ {nb(veg_ouvert)} ha. La BD TOPO ne distingue pas les friches et garrigues basses : leur surface exacte n'est pas connue. Les zonages forts couvrent {nb(z1 * 100)} % de la zone rapprochée. {znieff_txt}

{tab(hab_t)}
{img("habitats", "Carte des milieux")}
### 4.3 Eau et zones humides

Les parcelles n'ont aucun cours d'eau ni point d'eau. Le cours d'eau le plus proche, {eau[0] if eau else "non déterminé"}, est à {fr(eau[1], 0) if eau else "n.c."} m. Un bassin d'orage de l'autoroute, ouvrage artificiel intermittent, est à {fr(d_basin, 0) if d_basin is not None else "n.c."} m. Aucune zone humide n'est cartographiée sur les parcelles dans les couches consultées. L'orthophoto ne montre ni végétation de milieu humide ni dépression en eau. La caractérisation du sol selon l'arrêté de 2008 n'a pas été faite. Comme le sol n'est remanié que sur la voie d'accès pompier et que les écoulements ne sont pas modifiés, le projet n'a aucun effet sur l'hydrologie du site.
"""
    )

    # ------------------------------------------------------------------ 4
    pat_view = c.pat_band.copy()
    combo = sp.copy().astype(str)
    for g in combo.index:
        for col in combo.columns:
            combo.loc[g, col] = f"{int(sp.loc[g, col])} ({nb(c.obs_band.loc[g, col])})"
    combo = combo.reset_index().rename(columns={"groupe": "Espèces (observations)"})
    P.append(
        f"""## 5. Espèces

### 5.1 Nombre d'espèces selon la distance aux parcelles

Le tableau donne le nombre exact d'espèces et, entre parenthèses, d'observations par groupe et par bande de distance. Aucune observation n'existe sur les parcelles.

{tab(combo)}
{fig("fig_8", "Espèces par groupe et distance")}
### 5.2 Espèces patrimoniales et raisons de l'absence d'impact

Le tableau liste les espèces patrimoniales observées à moins de 2 km, avec leur nombre d'observations par bande. Au-delà de 2 km, aucune interaction directe avec les parcelles n'est identifiée : ces espèces sont listées en annexe A.

{tab(pat_view)}
Pour chaque espèce observée à moins de 1 km, le tableau suivant donne l'habitat dont elle a besoin et la raison pour laquelle le projet ne l'affecte pas. Les espèces observées entre 1 et 2 km sont traitées de la même façon en annexe C.

{tab(c.justif)}
### 5.3 Flore

Aucune observation de flore n'existe sur les parcelles. À moins de 1 km, {nb(fl["n_obs_zer"])} observations concernent {nb(fl["n_sp_zer"])} espèces, relevées par les conservatoires botaniques. {flora_zer_txt} La pression d'inventaire floristique est forte : {nb(fl["n_obs_zee"])} observations de {nb(fl["n_sp_zee"])} espèces dans les 5 km. {flora_pat_txt} Le sol n'est remanié que sur la voie d'accès pompier (moins de 400 m²) : la flore des parcelles est conservée pour l'essentiel.

### 5.4 Chiroptères

Les chauves-souris sont présentes dans le secteur. Les données précises n'en contiennent aucune. Les observations imprécises en donnent {bats_n} espèces et {nb(bats_obs)} relevés distincts, issus surtout de suivis acoustiques de parcs éoliens voisins (2021 et 2022), positionnés au centre d'une maille d'environ 5 km. Elles montrent que ces espèces fréquentent la région, pas qu'elles utilisent les parcelles. {bats_dom}

Les parcelles n'ont ni arbre, ni cavité, ni bâti : elles n'offrent aucun gîte. Les arbres gîtes éventuels se trouvent dans la pinède voisine, que le projet ne touche pas. Les fiches des sites Natura 2000 voisins placent les gîtes de ces espèces dans des grottes, des mines et des arbres, et citent l'entretien de milieux ouverts pour leur chasse. Le projet n'a aucun éclairage permanent et conserve une végétation basse, source d'insectes : la ressource de chasse est maintenue. Aucun effet sur les gîtes n'est donc possible.

{tab(c.bats.head(6))}
### 5.5 Oiseaux

Les oiseaux patrimoniaux signalés à moins de 1 km sont, pour la plupart, des rapaces et des oiseaux de passage ou de chasse. Leurs sites de reproduction sont des arbres, des cavités ou des falaises absents des parcelles. Pour les espèces qui chassent, l'emprise de {fr(ha, 2)} ha est une très petite part de territoires de chasse de plusieurs centaines à plusieurs milliers d'hectares. La zone de chasse se déplace au plus vers les milieux voisins, qui couvrent {nb(veg_ouvert)} ha dans la zone rapprochée. Pour les espèces nicheuses au sol, un écologue passe avant le chantier pour rechercher les nids et baliser les zones sensibles, et aucun travail n'a lieu d'avril à juillet. L'autoroute, à {fr(d_a9 or 0, 0)} m, est une source de bruit permanente à proximité immédiate des parcelles.

### 5.6 Odonates

Les odonates ont une larve aquatique : elles se développent dans l'eau. Les parcelles n'ont ni eau courante ni eau stagnante. Elles ne sont donc pas un habitat de reproduction. {c.odonata["txt"]} Le projet ne prélève ni ne rejette d'eau.

### 5.7 Reptiles et amphibiens

{rept_txt} {lezard_txt} Les amphibiens (Rainette méridionale, Crapaud calamite) se reproduisent dans l'eau, absente des parcelles. Le sol n'est remanié que sur la voie d'accès pompier, des passages de 15 sur 15 cm sont prévus dans la clôture et des pierriers servent d'abris.

### 5.8 Plans nationaux d'actions

Le tableau donne la présence des espèces citées par l'avis. Aucune n'est signalée sur les parcelles. Aucune ne dépend d'un habitat que le projet détruit.

{tab(c.pna)}
Le projet est plutôt favorable à ces espèces. La végétation basse est conservée et entretenue sans produit phytosanitaire, ce qui maintient les insectes et les reptiles dont se nourrissent le Lézard ocellé, la Pie-grièche à tête rousse, le Faucon crécerellette et les rapaces. Les pierriers offrent des abris. L'entretien régulier évite l'embroussaillement et l'incendie, deux causes de fermeture des milieux citées par les fiches des sites voisins.
"""
    )

    # ------------------------------------------------------------------ 5
    n2k_txt = ""
    for s in c.n2k:
        shared = s["shared"]
        sh_txt = (
            "Espèces du site Natura 2000 signalées à moins de 1 km des parcelles : "
            + ", ".join(shared)
            + ". Chacune est traitée au chapitre 5."
            if shared
            else "Aucune espèce du site Natura 2000 n'est signalée à moins de 1 km des parcelles."
        )
        if s.get("shared_coarse"):
            sh_txt += (
                " Des espèces du site Natura 2000 sont aussi signalées dans le secteur par des observations imprécises (maille d'environ 5 km) : "
                + ", ".join(s["shared_coarse"])
                + ". Ces observations ne permettent pas de dire que ces espèces fréquentent les parcelles."
            )
        n2k_txt += f"""### 6.{s["i"]} {s["type"]} {s["nom"]} ({s["code"]})

Distance aux parcelles : {fr(s["dist_km"], 2)} km. Surface du site : {nb(s["surface_ha"])} ha, {s["designation"]}. Les parcelles représentent {fr(ha / s["surface_ha"] * 100, 3)} % de la surface du site Natura 2000.

Pourquoi le site Natura 2000 est classé. {s["classement"]} {s["milieux"]} Objectifs du site Natura 2000 : {s["objectifs"][0].lower() + s["objectifs"][1:]}

{sh_txt}

Pourquoi le projet n'impacte pas les espèces et habitats du site Natura 2000. {s["pourquoi"]}

"""
    P.append(
        f"""## 6. Zonages et réglementation

Le tableau liste les zonages de protection et d'inventaire dans un rayon de 5 km.

{tab(c.protected)}
{img("natura", "Sites Natura 2000")}
Les parcelles ne recoupent aucun zonage. Le ZNIEFF de type I le plus proche est à {fr(d_fort / 1000, 2) if d_fort else "n.c."} km. Un ZNIEFF est un inventaire sans portée réglementaire directe. Le site Natura 2000 le plus proche est à {fr(zsc["dist_km"], 2) if zsc else "n.c."} km. Les parcelles sont hors de ces sites. Les liens éventuels passent par les espèces mobiles, traitées au chapitre 5.

{n2k_txt}
"""
    )

    # ------------------------------------------------------------------ 6
    inc = c.incidences
    inc_t = (
        inc.rename(
            columns={
                "groupe": "Groupe",
                "species": "Espèce",
                "sens_solaire": "Sensibilité",
                "n": "Obs. ZER",
            }
        )
        .head(6)
        .reset_index(drop=True)
        if len(inc)
        else inc
    )
    if len(inc_t):
        inc_t["Espèce"] = [
            f"{e} ({n})" if n else e
            for e, n in zip(inc_t["Espèce"], inc_t["nom_commun"], strict=True)
        ]
        inc_t = inc_t.drop(columns="nom_commun")
    P.append(
        f"""## 7. Incidences du projet

### 7.1 Sur les habitats

L'emprise est de {fr(ha, 2)} ha. {
            pj.get("sol_court", "")
        } La végétation basse des parcelles est conservée. Les milieux voisins (vignes, pinède, haies, cours d'eau) ne sont pas touchés.

### 7.2 Sur les espèces

Le tableau classe les espèces patrimoniales de la zone rapprochée par sensibilité à un parc solaire (jugement d'expert générique).

{tab(inc_t)}
En travaux, les risques courants sont la destruction de nichées, la mortalité de petits animaux, le compactage du sol et le dérangement. Ici, les travaux sont légers et limités en durée et en emprise : pas de terrassement ni de décapage hors de la voie d'accès pompier, pas d'engin lourd, pas de travaux d'avril à juillet, passage d'un écologue avant le démarrage. Ces risques sont donc fortement réduits. En exploitation, les panneaux créent de l'ombre sur une surface réduite. Les clôtures sont rendues perméables à la petite faune.

Les panneaux sont inclinés à 15°, donc non horizontaux, disposés en rangées discontinues séparées par des inter-rangs enherbés. La surface n'est ni horizontale ni continue : elle ne peut pas être confondue avec une étendue d'eau par les insectes aquatiques, les oiseaux d'eau ou les chauves-souris.

### 7.3 Espèces exotiques envahissantes

Le risque principal est l'apport de graines par les engins et le développement d'espèces opportunistes sur sol nu. Le projet limite ce risque de trois façons : le sol n'est pas mis à nu hors de la voie d'accès pompier, les engins sont nettoyés en sortie de chantier, et le terrain est entretenu régulièrement. Une végétation basse et continue, entretenue par une fauche annuelle tardive, laisse peu de place aux espèces envahissantes. Le contrôle des plantes invasives fait partie du suivi annuel.

### 7.4 Bénéfices attendus (hypothèses)

Quatre hypothèses de bénéfice sont retenues pour la biodiversité. Elles sont à confirmer par le suivi.

{
            tab(
                pd.DataFrame(
                    [
                        [
                            "Entretien régulier : une fauche annuelle tardive, un contrôle des clôtures et des invasives",
                            "Le milieu reste ouvert, sans fermeture par les ligneux, et le risque d'incendie diminue. Les plantes fleurissent et fructifient, ce qui nourrit les insectes, base du régime de nombreux oiseaux et chauves-souris.",
                        ],
                        [
                            "Aucun produit phytosanitaire",
                            "Insectes, reptiles et oiseaux insectivores gardent leur nourriture. Les fiches des sites Natura 2000 voisins citent ces produits parmi les menaces.",
                        ],
                        [
                            "Pierriers et passages dans la clôture",
                            "Abris pour les reptiles et la petite faune, qui circulent librement.",
                        ],
                        [
                            "Contrôle des espèces exotiques envahissantes",
                            "Le terrain est surveillé et entretenu, ce qui n'est pas le cas d'une friche non gérée.",
                        ],
                    ],
                    columns=["Pratique du projet", "Bénéfice attendu"],
                )
            )
        }
"""
    )

    # ------------------------------------------------------------------ 7
    P.append(
        """## 8. Mesures d'évitement et de réduction

Il n'y a pas de chantier lourd. Les travaux sont légers, limités en durée et en emprise. Les mesures suivent les prescriptions de l'avis de la DDTM.

| Thème | Mesure | Type | Effort |
|---|---|---|---|
| Sol | Aucun remaniement du sol, sauf la voie d'accès pompier de moins de 400 m², accessible depuis l'extérieur du site pour la défense incendie. | Éviter | Faible |
| Chantier | Chantier léger, limité en durée et en emprise, sans engin lourd, mené sans interruption longue pour éviter la réinstallation de la faune. Ni débroussaillage ni démarrage des travaux entre début avril et fin juillet. | Éviter, réduire | Faible |
| Chantier | Passage d'un écologue avant le démarrage du chantier. Il recherche les nids d'oiseaux nichant au sol (Alouette lulu, Pipit rousseline, Bruant ortolan) et les reptiles, balise les zones sensibles et ajuste si nécessaire le phasage ou les zones d'intervention. | Éviter, réduire | Faible |
| Débroussaillage | Évacuation des gros résidus, qui servent de refuge aux reptiles et aux hérissons. | Réduire | Faible |
| Éclairage | Pas d'éclairage permanent. Sinon minuterie ou détection, LED ambrées de 590 nm, orientées vers le sol. | Réduire | Faible |
| Clôture | Grillage de 2 m au maximum, tête plane, poteaux pleins ou creux obturés. | Réduire | Faible |
| Passages | Ouvertures d'au moins 15 sur 15 cm tous les 20 m, vérifiées et entretenues. | Réduire | Faible à moyen |
| Espèces invasives | Nettoyage des engins en sortie de chantier, protocole validé par un coordinateur environnement. | Réduire | Faible |
| Gestion | Entretien régulier : une fauche annuelle tardive, aucun produit phytosanitaire, pierriers refuges. | Réduire, accompagner | Moyen |
| Suivi | Contrôle annuel des clôtures, des haies et des plantes invasives. | Suivi | Moyen |
| Compensation | Aucun impact résiduel significatif n'est identifié : aucune compensation n'est nécessaire. | Compenser | Nul |

"""
    )

    # ------------------------------------------------------------------ 8
    P.append(
        f"""## 9. Réponse point par point à l'avis de la DDTM

Le tableau reprend chaque demande de l'avis de la DDTM, la réponse apportée par ce dossier et l'endroit où la trouver.

{tab(resp)}
"""
    )

    # ------------------------------------------------------------------ 9
    P.append(
        f"""## 10. Effets cumulés

Les parcs photovoltaïques recensés dans la zone d'étude éloignée (5 km) sont listés ci-dessous. Les parcs considérés dans la prise en compte des effets cumulés le sont à partir de l'autorisation d'urbanisme obtenue.

{tab(pv_t)}
Les parcs éoliens recensés dans la zone d'étude éloignée (5 km) sont listés ci-dessous, par commune et par année de mise en service (source : OpenStreetMap).

{tab(wind_t)}
Les parcs photovoltaïques considérés ont été construits après réalisation d'une étude d'impact sur l'environnement qui a conclu à des incidences non significatives à nulles. Le projet étudié et l'analyse des données GBIF permettent de conclure à des incidences non significatives sur l'environnement du site. La distance des parcs recensés au projet étudié et les surfaces considérées permettent de conclure que les effets cumulés sont non significatifs.

Les effets des éoliennes portent surtout sur la mortalité des oiseaux et des chauves-souris par collision. Le parc solaire n'ajoute pas de risque de collision, n'a pas d'éclairage permanent et conserve une végétation basse : les effets cumulés restent non significatifs.
"""
    )

    # ------------------------------------------------------------------ 8, 9
    P.append(
        f"""## 11. Conclusion

Les données historiques ne montrent aucun élément concret qui empêche le développement de la centrale.

Les parcelles sont hors ZNIEFF et hors site Natura 2000. Les {n_patri_zer} espèces patrimoniales signalées à moins de 1 km ne dépendent d'aucun habitat des parcelles : leurs sites de reproduction sont des arbres, des cavités, des falaises, l'eau ou des milieux ouverts bien plus vastes. Le projet ne remanie le sol que pour la voie d'accès pompier (moins de 400 m²), n'a pas de chantier lourd, n'utilise aucun produit phytosanitaire et entretient le terrain par une fauche annuelle tardive. Les chauves-souris sont présentes dans le secteur, mais les parcelles n'offrent aucun gîte. L'autoroute A9, à {fr(d_a9 or 0, 0)} m, borde le site.

Le projet conserve la végétation basse des parcelles et la fait entretenir régulièrement. Les mesures du chapitre 8 couvrent les risques résiduels, y compris pour les espèces que les données ne permettent pas de situer précisément : chantier limité en durée et en emprise, aucun débroussaillage ni démarrage des travaux d'avril à fin juillet, passage d'un écologue avant le démarrage pour rechercher les nids au sol et les reptiles et baliser les zones sensibles, gestion du couvert végétal et absence de produit phytosanitaire.

## 12. Limites

Les données GBIF viennent d'observateurs : elles donnent une image du secteur, avec les biais décrits au chapitre 3. Aucune observation n'existe sur les parcelles. Les {nb(cn["imprecis"])} observations imprécises sont analysées à part.

Les statuts de protection viennent d'un dictionnaire interne et seront confirmés sur TAXREF avant dépôt. La catégorie UICN est la catégorie mondiale fournie par GBIF.

La sensibilité au solaire est un jugement d'expert. Les informations sur le projet (sol, chantier, entretien, produits phytosanitaires, parcs voisins) viennent du porteur de projet. Les raisons d'absence d'impact reposent sur les habitats connus de chaque espèce et sur la géométrie du site. Ce diagnostic est documentaire.

### Liste des annexes

{tab(pd.DataFrame([["Annexe A", "Tableau récapitulatif des espèces patrimoniales, par bande de distance"], ["Annexe B", "Observations imprécises (plus de 1 km) : espèces patrimoniales"], ["Annexe C", "Raisons de l'absence d'impact pour les espèces observées entre 1 et 2 km"]], columns=["Annexe", "Contenu"]))}
Sources : GBIF, INPN (WFS Géoplateforme), BD TOPO, RPG, parcs photovoltaïques de l'IGN, parcs éoliens d'OpenStreetMap, fiches des sites Natura 2000 (DREAL Occitanie).
"""
    )

    return "\n".join(P)


def build_annexes(c: Case) -> str:
    """Annexes (separate PDF): recap table of patrimonial species and imprecise observations."""
    ci = c.coarse_info
    return f"""## Annexes

### Annexe A. Tableau récapitulatif des espèces patrimoniales

Le tableau donne les observations précises par bande de distance. La colonne Imprécises donne les observations placées au centre d'une maille d'environ 5 km.

{tab(c.annex_a)}
### Annexe B. Observations imprécises (plus de 1 km)

{nb(ci["n_obs"])} observations pour {nb(ci["n_species"])} espèces. Le tableau liste les {len(c.coarse_table)} espèces patrimoniales.

{tab(c.coarse_table)}
### Annexe C. Raisons de l'absence d'impact pour les espèces observées entre 1 et 2 km

{tab(c.justif_far)}
"""
