"""Taxonomic groups, protection status and solar sensitivity of GBIF species.

TAXREF / INPN status services were offline when this was written (the MNHN site was being
rebuilt after a cyber-attack), so protection and directive annexes come from the **indicative
dictionaries below**; the IUCN category is the *global* one GBIF returns, not the French Red
List. Treat every status as a first filter to confirm on TAXREF / regional lists.
"""

from __future__ import annotations

import pandas as pd

# Game birds and pests the national bird protection order (2009-10-29) does not cover.
BIRDS_NOT_PROTECTED = {
    "Anas platyrhynchos",
    "Columba palumbus",
    "Phasianus colchicus",
    "Alectoris rufa",
    "Perdix perdix",
    "Corvus corone",
    "Corvus frugilegus",
    "Pica pica",
    "Garrulus glandarius",
    "Sturnus vulgaris",
    "Turdus merula",
    "Turdus philomelos",
    "Turdus iliacus",
    "Turdus viscivorus",
    "Turdus pilaris",
    "Fulica atra",
    "Streptopelia decaocto",
    "Streptopelia turtur",
    "Columba livia",
    "Corvus monedula",
    "Anser anser",
    "Scolopax rusticola",
    "Coturnix coturnix",
    "Lepus europaeus",
    "Larus michahellis",
    "Branta canadensis",
}
BIRDS_ANNEX_I = {  # Birds Directive, annex I
    "Lanius collurio",
    "Circus aeruginosus",
    "Circus pygargus",
    "Circus cyaneus",
    "Circaetus gallicus",
    "Pernis apivorus",
    "Falco peregrinus",
    "Milvus milvus",
    "Milvus migrans",
    "Caprimulgus europaeus",
    "Burhinus oedicnemus",
    "Emberiza hortulana",
    "Curruca undata",
    "Sylvia undata",
    "Lullula arborea",
    "Alcedo atthis",
    "Bubo bubo",
    "Aquila fasciata",
    "Hieraaetus pennatus",
    "Aquila chrysaetos",
    "Tetrax tetrax",
    "Coracias garrulus",
    "Melanocorypha calandra",
    "Calandrella brachydactyla",
    "Anthus campestris",
    "Ardea purpurea",
    "Egretta garzetta",
    "Nycticorax nycticorax",
    "Ixobrychus minutus",
    "Pyrrhocorax pyrrhocorax",
    "Ciconia ciconia",
    "Neophron percnopterus",
    "Gyps fulvus",
    "Himantopus himantopus",
    "Recurvirostra avosetta",
    "Phoenicopterus roseus",
    "Botaurus stellaris",
    "Ardeola ralloides",
    "Bubulcus ibis",
    "Pluvialis apricaria",
    "Falco naumanni",
    "Oenanthe leucura",
    "Sterna hirundo",
    "Gelochelidon nilotica",
    "Larus melanocephalus",
    "Ficedula albicollis",
    "Dryocopus martius",
    "Dendrocopos medius",
    "Pandion haliaetus",
    "Platalea leucorodia",
    "Plegadis falcinellus",
}
# Habitats Directive. Bats: all annex IV, plus annex II for the species below.
BATS_ANNEX_II = {
    "Rhinolophus ferrumequinum",
    "Rhinolophus hipposideros",
    "Rhinolophus euryale",
    "Miniopterus schreibersii",
    "Myotis myotis",
    "Myotis blythii",
    "Myotis emarginatus",
    "Myotis capaccinii",
    "Myotis bechsteinii",
    "Barbastella barbastellus",
    "Rhinolophus mehelyi",
}
GENERA_ANNEX_IV = {  # reptiles / amphibians
    "Podarcis",
    "Lacerta",
    "Zootoca",
    "Coronella",
    "Zamenis",
    "Hierophis",
    "Elaphe",
    "Emys",
    "Testudo",
    "Hemidactylus",
    "Hyla",
    "Alytes",
    "Bufotes",
    "Epidalea",
    "Pelobates",
    "Triturus",
    "Mauremys",
}
ANNEX_II = {
    "Emys orbicularis",
    "Testudo hermanni",
    "Mauremys leprosa",
    "Lucanus cervus",
    "Cerambyx cerdo",
    "Coenagrion mercuriale",
    "Oxygastra curtisii",
    "Euplagia quadripunctaria",
    "Lycaena dispar",
    "Euphydryas aurinia",
    "Gomphus graslinii",
    "Lutra lutra",
    "Castor fiber",
    "Callimorpha quadripunctaria",
}
ANNEX_IV_SPECIES = {
    "Zerynthia rumina",
    "Zerynthia polyxena",
    "Proserpinus proserpina",
    "Parnassius apollo",
    "Lopinga achine",
    "Saga pedo",
    "Genetta genetta",
    "Felis silvestris",
    "Cerambyx cerdo",
    "Lycaena dispar",
    "Coenonympha oedippus",
    "Euphydryas aurinia",
    "Lutra lutra",
    "Castor fiber",
}
MAMMALS_PROTECTED = {
    "Erinaceus europaeus",
    "Sciurus vulgaris",
    "Genetta genetta",
    "Felis silvestris",
    "Lutra lutra",
    "Castor fiber",
    "Muscardinus avellanarius",
    "Neomys fodiens",
    "Neomys anomalus",
    "Lynx lynx",
    "Canis lupus",
}
INSECTS_PROTECTED = {
    "Zerynthia rumina",
    "Zerynthia polyxena",
    "Cerambyx cerdo",
    "Coenonympha oedippus",
    "Euphydryas aurinia",
    "Phengaris arion",
    "Phengaris alcon",
    "Proserpinus proserpina",
    "Gomphus graslinii",
    "Coenagrion mercuriale",
    "Oxygastra curtisii",
    "Lycaena dispar",
    "Parnassius apollo",
    "Lopinga achine",
    "Saga pedo",
    "Graellsia isabellae",
    "Papilio alexanor",
    "Apatura metis",
    "Cordulegaster bidentata",
    "Gomphus flavipes",
    "Ophiogomphus cecilia",
}

# Local additions to "patrimonial" (beyond directive annexes and IUCN CR/EN/VU/NT), and species
# whose global IUCN category must not make them patrimonial (huntable, abundant in France).
PATRIMONIAL_EXTRA = {
    "Timon lepidus",
    "Lanius senator",
    "Saga pedo",
    "Zerynthia rumina",
    "Oenanthe hispanica",
    "Emys orbicularis",
    "Testudo hermanni",
}
NOT_PATRIMONIAL = {
    "Oryctolagus cuniculus",
    "Aesculus hippocastanum",
    "Sequoia sempervirens",
    "Cedrus atlantica",
}
# GBIF sometimes returns a dialect or odd vernacular name first: these French names are used instead.
FR_NAMES = {
    "Burhinus oedicnemus": "Œdicnème criard", "Timon lepidus": "Lézard ocellé",
    "Anguilla anguilla": "Anguille européenne", "Hyla meridionalis": "Rainette méridionale",
    "Hypsugo savii": "Vespère de Savi", "Pipistrellus kuhlii": "Pipistrelle de Kuhl",
    "Pandion haliaetus": "Balbuzard pêcheur", "Aquila clanga": "Aigle criard",
    "Gyps fulvus": "Vautour fauve", "Circaetus gallicus": "Circaète Jean-le-Blanc",
    "Lacerta bilineata": "Lézard à deux raies", "Podarcis liolepis": "Lézard catalan",
    "Podarcis muralis": "Lézard des murailles", "Epidalea calamita": "Crapaud calamite",
    "Pipistrellus pipistrellus": "Pipistrelle commune", "Pipistrellus pygmaeus": "Pipistrelle pygmée",
    "Eptesicus serotinus": "Sérotine commune", "Nyctalus leisleri": "Noctule de Leisler",
    "Tadarida teniotis": "Molosse de Cestoni", "Miniopterus schreibersii": "Minioptère de Schreibers",
    "Zerynthia polyxena": "Diane", "Cneorum tricoccon": "Camélée à trois coques",
}  # fmt: skip

# Sensitivity to a ground-mounted solar park: expert judgement, species first then group.
SOLAR_BY_SPECIES = {
    "Burhinus oedicnemus": "Forte",
    "Tetrax tetrax": "Forte",
    "Melanocorypha calandra": "Forte",
    "Calandrella brachydactyla": "Forte",
    "Anthus campestris": "Forte",
    "Emberiza hortulana": "Forte",
    "Circus pygargus": "Forte",
    "Testudo hermanni": "Forte",
    "Lullula arborea": "Modérée",
    "Alauda arvensis": "Modérée",
    "Galerida theklae": "Modérée",
    "Galerida cristata": "Modérée",
    "Lanius senator": "Modérée",
    "Timon lepidus": "Modérée",
    "Zerynthia rumina": "Modérée",
    "Saga pedo": "Modérée",
    "Lanius collurio": "Faible",
    "Curruca undata": "Faible",
    "Sylvia undata": "Faible",
    "Circaetus gallicus": "Faible",
    "Aquila fasciata": "Faible",
    "Falco peregrinus": "Faible",
    "Emys orbicularis": "Faible",
}
SOLAR_BY_GROUP = {
    "Oiseaux": "Modérée",
    "Chiroptères": "Faible",
    "Mammifères": "Faible",
    "Reptiles": "Faible",
    "Amphibiens": "Faible",
    "Insectes": "Modérée",
    "Flore vasculaire": "Forte",
}


def taxon_group(kingdom: str | None, phylum: str | None, cls: str | None, order: str | None) -> str:
    """Report group (French labels) from the GBIF taxonomy fields."""
    if kingdom == "Animalia":
        if cls == "Aves":
            return "Oiseaux"
        if cls == "Mammalia":
            return "Chiroptères" if order == "Chiroptera" else "Mammifères"
        # GBIF names the lizard and snake class "Squamata" and the turtle class "Testudines"
        return {
            "Reptilia": "Reptiles", "Squamata": "Reptiles", "Testudines": "Reptiles",
            "Crocodylia": "Reptiles", "Amphibia": "Amphibiens", "Insecta": "Insectes",
        }.get(cls or "", "Autres faune")  # fmt: skip
    if kingdom == "Plantae":
        return "Flore vasculaire" if phylum == "Tracheophyta" else "Flore non-vasculaire"
    return "Champignons" if kingdom == "Fungi" else "Autres"


def protection(species: str, genus: str | None, group: str) -> tuple[bool, str]:
    """(nationally protected, EU directive label) for a species — indicative, see module doc."""
    directive = ""
    if group == "Oiseaux":
        if species in BIRDS_ANNEX_I:
            directive = "DO Ann. I"
        return species not in BIRDS_NOT_PROTECTED, directive
    if group == "Chiroptères":
        return True, "DHFF Ann. II+IV" if species in BATS_ANNEX_II else "DHFF Ann. IV"
    if group in ("Reptiles", "Amphibiens", "Mammifères", "Insectes"):
        if species in ANNEX_II:
            directive = "DHFF Ann. II+IV" if group != "Insectes" else "DHFF Ann. II"
        elif species in ANNEX_IV_SPECIES or (
            group in ("Reptiles", "Amphibiens") and genus in GENERA_ANNEX_IV
        ):
            directive = "DHFF Ann. IV"
        if group in ("Reptiles", "Amphibiens"):
            return True, directive  # nearly all native species are protected
        known = MAMMALS_PROTECTED if group == "Mammifères" else INSECTS_PROTECTED
        return species in known, directive
    return False, ""


def solar_sensitivity(species: str, group: str) -> str:
    return SOLAR_BY_SPECIES.get(species, SOLAR_BY_GROUP.get(group, "Faible"))


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add group, protection, directive, IUCN, solar sensitivity and patrimonial flags."""
    out = df.copy()
    out["groupe"] = [
        taxon_group(k, p, c, o)
        for k, p, c, o in zip(out.kingdom, out.phylum, out["class"], out["order"], strict=True)
    ]
    st = [
        protection(s, g, grp) for s, g, grp in zip(out.species, out.genus, out.groupe, strict=True)
    ]
    out["protege_fr"] = [s[0] for s in st]
    out["directive"] = [s[1] for s in st]
    out["uicn"] = out.iucnRedListCategory.fillna("NE")
    out["menace"] = out.uicn.isin(["CR", "EN", "VU"])
    out["sens_solaire"] = [
        solar_sensitivity(s, g) for s, g in zip(out.species, out.groupe, strict=True)
    ]
    out["sensible"] = out.protege_fr | out.menace | (out.directive != "")
    out["patrimoniale"] = (
        out.sensible
        & ~out.species.isin(NOT_PATRIMONIAL)
        & (
            (out.directive != "")
            | out.menace
            | (out.uicn == "NT")
            | out.species.isin(PATRIMONIAL_EXTRA)
        )
    )
    return out
