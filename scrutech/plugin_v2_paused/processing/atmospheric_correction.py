"""Correction atmosphérique — Palier 4.

Petites zones : wrapper Sen2Cor local. Sinon, priorise dans la recherche
STAC les produits déjà corrigés (Sentinel-2 L2A) plutôt que de recorriger.
"""


class AtmosphericCorrectionProcessor:
    def is_already_corrected(self, collection: str) -> bool:
        """Sentinel-2 L2A est déjà corrigé — éviter tout retraitement inutile."""
        raise NotImplementedError

    def run_sen2cor_local(self, l1c_product_path: str) -> str:
        raise NotImplementedError
