"""Cache local borné — jamais de téléchargement silencieux d'une scène complète.

Contrainte d'implémentation n°3 : taille max configurable (défaut 2 Go),
purge LRU.
"""

DEFAULT_MAX_CACHE_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 Go


class CacheManager:
    def __init__(self, max_size_bytes: int = DEFAULT_MAX_CACHE_SIZE_BYTES):
        self.max_size_bytes = max_size_bytes

    def current_size_bytes(self) -> int:
        raise NotImplementedError

    def add(self, key: str, file_path: str) -> None:
        """Ajoute une entrée, purge LRU si max_size_bytes dépassé."""
        raise NotImplementedError

    def get(self, key: str) -> str | None:
        raise NotImplementedError

    def purge_lru_until_under_limit(self) -> None:
        raise NotImplementedError
