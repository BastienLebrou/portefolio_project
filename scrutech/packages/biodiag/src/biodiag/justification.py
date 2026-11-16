"""Species-by-species reasoning: habitat the species needs and why the project does not affect it.

Short factual sentences. The habitat sentences are general ecology of each species; the reasons are
built from measured facts of the site (parcel area, open habitats in the ZER, distances to water)
and from the project facts given by the developer. Nothing here replaces a field survey: it states
what the bibliography and the site geometry allow to conclude.
"""

from __future__ import annotations

# species -> (category, habitat requirement)
SPECIES: dict[str, tuple[str, str]] = {
    "Lullula arborea": ("sol_ouvert", "Nicheur au sol dans les milieux ouverts à arbres et buissons dispersés."),
    "Anthus campestris": ("sol_ouvert", "Nicheur au sol dans les milieux secs à végétation rase et sol nu."),
    "Emberiza hortulana": ("sol_ouvert", "Nicheur au sol sur les coteaux secs, cultures en terrasses et vignes avec haies."),
    "Burhinus oedicnemus": ("sol_ouvert", "Nicheur au sol dans les terrains ouverts et caillouteux de grande étendue."),
    "Circus pygargus": ("sol_ouvert", "Nicheur au sol dans les cultures céréalières et les landes ouvertes."),
    "Tetrax tetrax": ("sol_ouvert", "Vit dans les plaines cultivées et les steppes. Il demande de vastes espaces ouverts."),
    "Caprimulgus europaeus": ("sol_ouvert", "Nicheur au sol dans les landes et boisements clairs. Actif de nuit."),
    "Sylvia undata": ("buisson", "Nicheuse dans les landes et garrigues hautes denses."),
    "Lanius senator": ("buisson", "Nicheuse dans les haies et arbres épars en milieu ouvert."),
    "Lanius meridionalis": ("buisson", "Nicheuse dans les buissons des garrigues ouvertes."),
    "Lanius collurio": ("buisson", "Nicheuse dans les buissons épineux et les haies."),
    "Coracias garrulus": ("chasse_cavite", "Niche dans des cavités (arbres creux, murs). Chasse de gros insectes en milieu ouvert."),
    "Streptopelia turtur": ("arbre", "Nicheuse dans les haies, bosquets et lisières arborées."),
    "Circaetus gallicus": ("chasse_arbre", "Rapace qui niche dans les arbres et chasse les reptiles sur plusieurs milliers d'hectares."),
    "Milvus migrans": ("chasse_arbre", "Rapace qui niche dans les arbres, souvent près des cours d'eau, aux proies variées."),
    "Milvus milvus": ("chasse_arbre", "Rapace qui niche dans de grands arbres et chasse en milieu ouvert sur de grands territoires."),
    "Pernis apivorus": ("arbre", "Rapace forestier qui niche dans les arbres."),
    "Hieraaetus pennatus": ("chasse_arbre", "Rapace qui niche dans les arbres et chasse sur de grands territoires."),
    "Bubo bubo": ("falaise", "Rapace nocturne qui niche en falaise ou carrière."),
    "Gyps fulvus": ("falaise", "Vautour qui niche en falaise et survole de vastes territoires."),
    "Aquila chrysaetos": ("falaise", "Rapace qui niche en falaise et chasse sur de très grands territoires."),
    "Falco peregrinus": ("falaise", "Faucon qui niche en falaise."),
    "Circus aeruginosus": ("eau", "Rapace qui niche dans les roselières et zones humides."),
    "Circus cyaneus": ("sol_ouvert", "Hivernant dans les plaines ouvertes."),
    "Alcedo atthis": ("eau", "Oiseau lié aux cours d'eau poissonneux à berges meubles."),
    "Hyla meridionalis": ("eau_amphibien", "Se reproduit dans les mares et vit dans la végétation proche."),
    "Epidalea calamita": ("eau_amphibien", "Se reproduit dans les flaques temporaires et vit dans les sols meubles."),
    "Triturus marmoratus": ("eau_amphibien", "Se reproduit en mares et vit sous des abris humides."),
    "Zerynthia polyxena": ("plante_insecte", "Papillon dont la chenille se nourrit d'aristoloches, en milieu frais."),
    "Cerambyx cerdo": ("arbre_insecte", "Insecte lié aux vieux chênes."),
    "Oxygastra curtisii": ("riviere", "Libellule liée aux rivières bordées d'arbres."),
    "Gomphus graslinii": ("riviere", "Libellule des grandes rivières."),
    "Anguilla anguilla": ("riviere", "Poisson migrateur qui vit dans les cours d'eau."),
    "Lacerta bilineata": ("reptile", "Lézard de milieux frais et denses : lisières, haies et friches herbeuses."),
    "Timon lepidus": ("reptile", "Lézard des garrigues, vignes et pierriers ensoleillés. Il a besoin d'abris (pierres, murets, terriers)."),
    "Podarcis muralis": ("reptile", "Petit lézard des murs, rochers et lisières."),
    "Podarcis liolepis": ("reptile", "Lézard des garrigues, pierriers et murets."),
    "Aquila clanga": ("passage", "Grand rapace très rare en France, de passage ou hivernant près des zones humides."),
    "Pandion haliaetus": ("passage", "Rapace pêcheur de passage, lié aux plans d'eau et aux rivières."),
    "Cneorum tricoccon": ("flore", "Arbrisseau des garrigues et pentes rocailleuses calcaires."),
}  # fmt: skip


def reason(category: str, f: dict) -> str:
    """Why the species is not affected, from the category and the measured site facts."""
    ha, ouvert, haie = f["area_ha"], f["open_ha"], f["hedge_ha"]
    ha_fr = f"{ha:.1f}".replace(".", ",")
    de, dh = f["d_water"], f["d_basin"]
    out = {
        "sol_ouvert": (
            "Mesures : écologue avant travaux (recherche des nids au sol), pas de travaux d'avril à juillet, sol non remanié hors voie "
            f"pompier, couvert bas entretenu par fauche tardive sans phytosanitaire. {ouvert:.0f} ha de milieux ouverts équivalents à proximité."
        ),
        "buisson": f"Mesures : haies et boisements voisins non touchés ({haie:.0f} ha de haies en ZER), pas de travaux d'avril à juillet, aucun éclairage permanent.",
        "chasse_cavite": (
            f"Aucun arbre ni cavité touché. Chasse en milieu ouvert maintenue par le couvert bas, sans phytosanitaire : {ha_fr} ha sur un "
            f"grand territoire, {ouvert:.0f} ha équivalents à proximité."
        ),
        "chasse_arbre": (
            f"Moins de 1 % d'un territoire de chasse de plusieurs milliers d'ha. Couvert bas conservé, sans phytosanitaire : {ouvert:.0f} ha "
            "de milieux ouverts équivalents en ZER. Aucun arbre de nidification touché."
        ),
        "arbre": "Aucun arbre ni bosquet touché. Boisements voisins non touchés, pas de travaux d'avril à juillet.",
        "arbre_insecte": "Aucun arbre coupé, aucun chêne ancien touché.",
        "falaise": "Ni falaise ni relief. L'espèce ne fait que survoler le secteur.",
        "eau": f"Eau et berges non touchées. Bassin d'orage de l'A9 (artificiel) à {dh:.0f} m, cours d'eau à {de:.0f} m.",
        "eau_amphibien": (
            f"Aucun point d'eau touché (bassin d'orage de l'A9 à {dh:.0f} m, cours d'eau à {de:.0f} m). Mesures : écologue avant travaux, "
            "sol non remanié hors voie pompier, passages de 15 sur 15 cm dans la clôture, pierriers refuges."
        ),
        "plante_insecte": "Mesures : sol non remanié hors voie pompier, couvert végétal conservé, fauche tardive, sans phytosanitaire. Plantes et insectes maintenus.",
        "riviere": f"Espèce de l'eau courante ; cours d'eau à {de:.0f} m. Aucun prélèvement ni rejet d'eau, berges non touchées.",
        "flore": "Sol non remanié hors voie pompier, couvert végétal conservé, fauche tardive. Aucune observation de l'espèce en ZER.",
        "reptile": (
            "Mesures : écologue avant travaux, pas de débroussaillage d'avril à juillet, sol non remanié hors voie pompier, pierriers refuges, "
            "passages de 15 sur 15 cm dans la clôture, végétation basse sans phytosanitaire."
        ),
        "passage": "Espèce de passage, sans lien avec les parcelles. Le projet ne touche ni plan d'eau ni rivière.",
    }
    return out.get(
        category,
        "Aucun lien avec le projet n'est identifié. Travaux limités, pas de travaux d'avril à juillet, écologue avant travaux.",
    )


def justify(species: str, dmin: float, facts: dict) -> tuple[str, str]:
    """(habitat requirement, why not affected) for one species."""
    cat, habitat = SPECIES.get(species, ("autre", "Voir la fiche de l'espèce sur l'INPN."))
    if dmin > 2000:
        return habitat, "Observée à plus de 2 km des parcelles. Aucun lien avec le projet."
    return habitat, reason(cat, facts)
