"""Tests stac_client — tous les appels HTTP sont mockés (responses/pytest-mock).
Aucun test de cette suite ne doit toucher le réseau réel.
"""

import pytest


@pytest.mark.skip(reason="scaffold — implémenter après stac_client.py")
def test_search_merges_cdse_and_mpc_results():
    ...


@pytest.mark.skip(reason="scaffold — implémenter après stac_client.py")
def test_search_deduplicates_overlapping_scenes():
    ...
