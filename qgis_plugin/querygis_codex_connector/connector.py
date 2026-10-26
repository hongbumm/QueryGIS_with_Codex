"""QGIS companion: connects to the existing plugin, never replaces its UI or AI."""
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject, Qgis
from qgis.utils import plugins, pluginMetadata

from .adapter import ExistingQueryGISAdapter
from .bridge import BridgeServer
from .tasks import TaskStore


class QueryGISCodexConnector(QObject):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.store = TaskStore()
        self.bridge = BridgeServer(self.store)
        self.adapter = None
        self.action = None
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._tick)

    def initGui(self):
        self.action = QAction(QIcon(str(Path(__file__).with_name("icon.png"))), "QueryGIS ↔ Codex 연결", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle)
        self.iface.addPluginToMenu("&QueryGIS", self.action)
        self.iface.addToolBarIcon(self.action)

    def _find_querygis(self):
        candidates = []
        for name, target in plugins.items():
            if target is self or "with_codex" in name.lower():
                continue
            if (str(pluginMetadata(name, "name") or "").strip() == "QueryGIS" and
                    all(callable(getattr(target, method, None)) for method in ExistingQueryGISAdapter.REQUIRED)):
                candidates.append(target)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise RuntimeError("QueryGIS가 여러 개 활성화되어 있습니다. 사용할 원본 QueryGIS 하나만 활성화하세요")
        raise RuntimeError("먼저 기존 QueryGIS 플러그인을 설치하고 활성화하세요")

    def toggle(self, checked=False):
        if self.bridge.running:
            self.disconnect()
            return
        try:
            target = self._find_querygis()
            target.run()
            self.adapter = ExistingQueryGISAdapter(target, self.store, QgsProject.instance())
            self.adapter.attach()
            self._refresh_snapshot()
            self.bridge.start()
            self.timer.start()
            self.action.setChecked(True)
            self.iface.messageBar().pushMessage("QueryGIS", "Codex 연결을 시작했습니다. 기존 QueryGIS의 Key와 서버를 사용합니다.", level=Qgis.Info)
        except Exception as exc:
            self.disconnect()
            self.iface.messageBar().pushMessage("QueryGIS", str(exc), level=Qgis.Warning)

    def _refresh_snapshot(self):
        project = QgsProject.instance()
        layers = [{"id": layer.id(), "name": layer.name(), "crs": layer.crs().authid()}
                  for layer in project.mapLayers().values()]
        self.bridge.set_snapshot({"querygis_ready": bool(self.adapter and self.adapter.ready),
                                  "layers": layers, "project_crs": project.crs().authid(),
                                  "execution_owner": "existing_querygis",
                                  "authentication": "querygis_service_key_or_existing_login"})

    def _tick(self):
        try:
            if self.adapter:
                self._refresh_snapshot()
                self.adapter.poll()
        except Exception as exc:
            if self.adapter and self.adapter.active:
                self.adapter._handle_error(str(exc))
            else:
                self.disconnect()

    def disconnect(self):
        self.timer.stop()
        self.bridge.stop()
        self.store.cancel_all()
        if self.adapter:
            self.adapter.detach()
            self.adapter = None
        if self.action:
            self.action.setChecked(False)

    def unload(self):
        self.disconnect()
        if self.action:
            self.iface.removePluginMenu("&QueryGIS", self.action)
            self.iface.removeToolBarIcon(self.action)
