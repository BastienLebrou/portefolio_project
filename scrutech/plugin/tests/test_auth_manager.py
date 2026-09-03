import pytest

# @pytest.mark.skip fait ignorer le test par pytest (il apparaît "SKIPPED" dans le
# rapport, ni réussi ni échoué) : utile ici car ces tests documentent déjà, par leur
# NOM, ce qu'il faudra vérifier une fois auth_manager.py réellement implémenté (voir
# ses `raise NotImplementedError`), sans faire échouer la suite en attendant.
# `...` (Ellipsis) est une syntaxe Python valide comme corps de fonction vide — un
# équivalent de `pass` un peu plus visuel pour marquer "à écrire".
@pytest.mark.skip(reason="scaffold — implémenter après auth_manager.py")
def test_save_credentials_never_returns_raw_key_value():
    ...


@pytest.mark.skip(reason="scaffold — implémenter après auth_manager.py")
def test_credentials_are_stored_via_qgs_auth_manager_not_plaintext():
    ...
