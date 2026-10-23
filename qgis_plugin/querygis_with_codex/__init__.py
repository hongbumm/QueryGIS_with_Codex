"""QGIS loads Qt and provider code only through its plugin entry point."""


def classFactory(iface):
    from .plugin import QueryGISWithCodex
    return QueryGISWithCodex(iface)
