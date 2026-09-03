"""Tests stac_client — tous les appels HTTP sont mockés (responses/pytest-mock).
Aucun test de cette suite ne doit toucher le réseau réel.
"""

# Même patron que test_auth_manager.py : tests "scaffold" désactivés (skip) qui
# documentent déjà par leur nom ce qu'il faudra vérifier une fois stac_client.py
# implémenté.
import pytest


@pytest.mark.skip(reason="scaffold — implémenter après stac_client.py")
def test_search_merges_cdse_and_mpc_results():
    ...


@pytest.mark.skip(reason="scaffold — implémenter après stac_client.py")
def test_search_deduplicates_overlapping_scenes():
    ...
