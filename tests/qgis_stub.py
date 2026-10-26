"""Small QGIS stand-in for real Qt UI/lifecycle tests, NOT a geometry test engine."""
import sys
import types
import uuid
from PyQt5 import QtCore, QtGui, QtWidgets


class CRS:
    def __init__(self, authid="EPSG:5179"):
        self._authid = authid

    def authid(self):
        return self._authid


class Extent:
    def xMinimum(self): return 0
    def yMinimum(self): return 0
    def xMaximum(self): return 1000
    def yMaximum(self): return 1000


class VectorLayer:
    def __init__(self, source="Point?crs=EPSG:5179", name="학교", provider="memory"):
        self._id, self._name, self._source = uuid.uuid4().hex, name, source

    def id(self): return self._id
    def name(self): return self._name
    def source(self): return self._source
    def type(self): return 0
    def crs(self): return CRS()
    def fields(self): return []
    def featureCount(self): return 1
    def getFeatures(self): return iter([])
    def wkbType(self): return 1
    def extent(self): return Extent()
    def isValid(self): return True
    def selectedFeatureCount(self): return 0


class RasterLayer:
    pass


class Project(QtCore.QObject):
    layersAdded = QtCore.pyqtSignal(list)
    layersRemoved = QtCore.pyqtSignal(list)
    _project = None

    def __init__(self):
        super().__init__()
        self.layers = {}
        self.execution_threads = []

    @classmethod
    def instance(cls):
        if cls._project is None:
            cls._project = cls()
        return cls._project

    def mapLayers(self): return dict(self.layers)
    def mapLayer(self, layer_id): return self.layers.get(layer_id)
    def mapLayersByName(self, name): return [layer for layer in self.layers.values() if layer.name() == name]
    def crs(self): return CRS()
    def title(self): return "Test project"
    def fileName(self): return ""
    def homePath(self): return ""

    def addMapLayer(self, layer):
        self.execution_threads.append(QtCore.QThread.currentThread())
        self.layers[layer.id()] = layer
        self.layersAdded.emit([layer])
        return layer


class Feedback:
    def __init__(self): self._cancelled = False
    def isCanceled(self): return self._cancelled
    def setProgress(self, progress): pass
    def pushInfo(self, message): pass


class MessageLog(QtCore.QObject):
    messageReceived = QtCore.pyqtSignal(str, str, int)


class Tree(QtWidgets.QTreeView):
    def __init__(self):
        super().__init__()
        self.setModel(QtGui.QStandardItemModel())

    def selectedLayers(self): return list(Project.instance().layers.values())[:1]


class Interface(QtCore.QObject):
    currentLayerChanged = QtCore.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.window = QtWidgets.QMainWindow()
        self.tree = Tree()

    def mainWindow(self): return self.window
    def layerTreeView(self): return self.tree
    def activeLayer(self): return next(iter(Project.instance().layers.values()), None)
    def addDockWidget(self, area, dock): self.window.addDockWidget(area, dock)
    def removeDockWidget(self, dock): self.window.removeDockWidget(dock)
    def addToolBarIcon(self, action): pass
    def addPluginToMenu(self, menu, action): pass
    def removePluginMenu(self, menu, action): pass
    def removeToolBarIcon(self, action): pass
    def messageBar(self): return self
    def pushMessage(self, *args, **kwargs): pass


def install():
    qgis = types.ModuleType("qgis")
    core = types.ModuleType("qgis.core")
    pyqt = types.ModuleType("qgis.PyQt")
    utils = types.ModuleType("qgis.utils")
    for name in ("QgsApplication", "QgsField", "QgsFeature", "QgsGeometry", "QgsPointXY", "QgsRectangle",
                 "QgsCoordinateReferenceSystem", "QgsVectorFileWriter", "QgsProcessingFeatureSourceDefinition",
                 "QgsFeatureSink", "QgsFeatureRequest", "QgsMessageLog", "QgsFillSymbol", "QgsSingleSymbolRenderer",
                 "QgsSymbol", "QgsRendererCategory", "QgsCategorizedSymbolRenderer", "QgsPalLayerSettings",
                 "QgsTextFormat", "QgsTextBufferSettings", "QgsVectorLayerSimpleLabeling", "QgsProperty"):
        setattr(core, name, type(name, (), {}))
    core.Qgis = type("Qgis", (), {"Critical": 2, "Info": 0, "Warning": 1, "QGIS_VERSION": "test-stub"})
    core.QgsMapLayer = type("QgsMapLayer", (), {"VectorLayer": 0, "RasterLayer": 1})
    core.QgsWkbTypes = type("QgsWkbTypes", (), {"displayString": staticmethod(lambda value: "Point")})
    core.QgsProject, core.QgsVectorLayer, core.QgsRasterLayer = Project, VectorLayer, RasterLayer
    core.QgsProcessingFeedback = Feedback
    log = MessageLog()
    core.QgsApplication.messageLog = staticmethod(lambda: log)
    pyqt.QtCore, pyqt.QtGui, pyqt.QtWidgets = QtCore, QtGui, QtWidgets
    utils.iface = None
    utils.plugins = {}
    utils.pluginMetadata = lambda name, field: "QueryGIS" if name == "query_gis" else name
    qgis.core, qgis.PyQt, qgis.utils = core, pyqt, utils
    for name, module in {"qgis": qgis, "qgis.core": core, "qgis.utils": utils, "qgis.PyQt": pyqt,
                         "qgis.PyQt.QtCore": QtCore, "qgis.PyQt.QtGui": QtGui,
                         "qgis.PyQt.QtWidgets": QtWidgets}.items():
        sys.modules[name] = module
    processing = types.ModuleType("processing")
    processing.run = lambda *args, **kwargs: {"OUTPUT": VectorLayer(name="buffer")}
    sys.modules["processing"] = processing
    for name in ("qgis.gui", "qgis.analysis"):
        module = types.ModuleType(name)
        module.__all__ = []
        sys.modules[name] = module
