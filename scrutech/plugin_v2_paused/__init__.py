def classFactory(iface):
    from .plugin import GeoDataEngineerPlugin

    return GeoDataEngineerPlugin(iface)
