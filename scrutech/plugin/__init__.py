# QGIS exige que le __init__.py de tout plugin définisse EXACTEMENT une fonction
# nommée `classFactory(iface)` : c'est le point d'entrée que QGIS appelle lui-même
# au chargement du plugin, qui doit renvoyer l'objet plugin (ici GeoDataEngineerPlugin,
# voir plugin.py). L'import est fait à l'intérieur de la fonction (pas en haut du
# fichier) pour que ce __init__.py reste importable même sans l'environnement QGIS
# complet — utile par exemple pour des outils qui inspectent le plugin sans le lancer.
def classFactory(iface):
    from .plugin import GeoDataEngineerPlugin

    return GeoDataEngineerPlugin(iface)
