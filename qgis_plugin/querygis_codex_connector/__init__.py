"""A connection companion for the existing QueryGIS QGIS plugin."""


def classFactory(iface):
    from .connector import QueryGISCodexConnector
    return QueryGISCodexConnector(iface)
