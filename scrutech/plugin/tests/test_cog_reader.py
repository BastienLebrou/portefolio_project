# Même patron que test_auth_manager.py : tests "scaffold" désactivés (skip) qui
# documentent déjà par leur nom ce qu'il faudra vérifier une fois cog_reader.py
# implémenté (voir ses `raise NotImplementedError`).
import pytest


@pytest.mark.skip(reason="scaffold — implémenter après cog_reader.py")
def test_open_as_layer_uses_vsicurl_uri_without_local_copy():
    ...


@pytest.mark.skip(reason="scaffold — implémenter après cog_reader.py")
def test_cache_locally_is_the_only_path_that_writes_a_full_file():
    ...
