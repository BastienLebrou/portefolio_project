"""Correction atmosphérique — Palier 4.

Petites zones : wrapper Sen2Cor local. Sinon, priorise dans la recherche
STAC les produits déjà corrigés (Sentinel-2 L2A) plutôt que de recorriger.
"""


# La correction atmosphérique retire l'effet de l'atmosphère (vapeur d'eau, aérosols...)
# sur les valeurs mesurées par le satellite, pour obtenir la vraie réflectance au sol.
# C'est un calcul lourd (Sen2Cor) : autant que possible on préfère récupérer une donnée
# DÉJÀ corrigée en amont (Sentinel-2 "L2A" l'est, contrairement au "L1C" brut) plutôt que
# la refaire nous-mêmes.
class AtmosphericCorrectionProcessor:
    def is_already_corrected(self, collection: str) -> bool:
        """Sentinel-2 L2A est déjà corrigé — éviter tout retraitement inutile."""
        raise NotImplementedError

    def run_sen2cor_local(self, l1c_product_path: str) -> str:
        raise NotImplementedError
