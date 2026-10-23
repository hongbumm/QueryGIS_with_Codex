"""QueryGIS remains the sole owner of planning, QGIS execution and corrections."""
import builtins
import contextlib
import io
import os
import traceback
import uuid
import threading
from pathlib import Path

import qgis.core as core
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer, QgsProcessingFeedback, Qgis
from qgis.PyQt.QtCore import QSettings, QObject, QTimer, pyqtSignal, Qt
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox,
                                QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
                                QWidget, QVBoxLayout, QTextEdit)

from .query_gis import QueryGIS
from .bridge import BridgeServer
from .provider import ProviderConfig, generate_plan
from .tasks import TaskStore, TERMINAL


class PlanWorker(QObject):
    planned = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)
    finished = pyqtSignal()

    def __init__(self, task_id, config, payload, context, correction=None):
        super().__init__()
        self.task_id, self.config = task_id, config
        self.payload, self.context, self.correction = payload, context, correction
        self._thread = threading.Thread(target=self.run, daemon=True, name="QueryGIS-AI-request")

    def start(self):
        self._thread.start()

    def isRunning(self):
        return self._thread.is_alive()

    def run(self):
        try:
            plan = generate_plan(self.config, self.payload["instruction"], self.context,
                                 self.payload["mode"], self.correction)
            self.planned.emit(self.task_id, plan)
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc).replace(self.config.api_key, "[REDACTED]"))
        finally:
            self.finished.emit()


class TaskFeedback(QgsProcessingFeedback):
    def __init__(self, cancel_event):
        super().__init__()
        self.cancel_event = cancel_event

    def isCanceled(self):
        return self.cancel_event.is_set() or super().isCanceled()


class QueryGISWithCodex(QueryGIS):
    def __init__(self, iface):
        super().__init__(iface)
        self.menu = "&QueryGIS with Codex"
        self.tasks = TaskStore()
        self.bridge = BridgeServer(self.tasks)
        self._session_key = ""
        self._active_task = None
        self._plan_worker = None
        self._task_context = None
        self._task_config = None
        self._plan = None
        self._correction_count = 0
        self._integration_ui = False
        self._closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def initGui(self):
        self.add_action(str(Path(__file__).with_name("icon.png")), "QueryGIS with Codex",
                        self.run, parent=self.iface.mainWindow())

    def load_api_key(self):
        return self._session_key

    def save_api_key(self, api_key):
        # Deliberately session-only. Base64 in QSettings is not encrypted storage.
        self._session_key = api_key

    def run(self):
        super().run()
        if not self._integration_ui:
            self._add_integration_ui()
        self.dockwidget.setWindowTitle("QueryGIS with Codex · 실험 버전")

    def _on_dockwidget_destroyed(self):
        # Closing the panel also closes its control endpoint.
        self.bridge.stop()
        self.tasks.cancel_all()
        self._integration_ui = False
        super()._on_dockwidget_destroyed()

    def _add_integration_ui(self):
        self.ui.dockWidgetContents.setStyleSheet("background-color: white; color: #1f2937;")
        self.ui.label_title.setText("QueryGIS with Codex")
        settings = QSettings()
        group = QGroupBox("AI 설정 · API Key는 현재 세션에만 보관")
        form = QFormLayout(group)
        self.provider_combo = QComboBox()
        for label, value in [("OpenAI API", "openai"), ("Google Gemini API", "gemini"),
                             ("기존 QueryGIS 서버", "backend")]:
            self.provider_combo.addItem(label, value)
        saved_provider = settings.value("QueryGISWithCodex/provider", "openai")
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(saved_provider)))
        self.model_input = QLineEdit(settings.value("QueryGISWithCodex/model/" + saved_provider,
                                                  "gpt-5.5" if saved_provider == "openai" else ""))
        self.model_input.setPlaceholderText("이 Key로 사용할 수 있는 모델명")
        self.backend_input = QLineEdit(settings.value("QueryGISWithCodex/backend", "http://127.0.0.1:5000"))
        form.addRow("AI 공급자", self.provider_combo)
        form.addRow("모델", self.model_input)
        form.addRow("QueryGIS 서버", self.backend_input)
        self.backend_label = form.labelForField(self.backend_input)
        self.ui.mainLayout.insertWidget(1, group)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self._provider_changed()
        self.ui.line_apikey.setPlaceholderText("선택한 AI 공급자의 API Key")
        self.ui.line_apikey.setText(self._session_key)

        controls = QGroupBox("Codex 연결 · GIS 작업은 QueryGIS에서 처리")
        layout = QFormLayout(controls)
        buttons = QHBoxLayout()
        self.connect_button = QPushButton("연결 시작")
        self.connect_button.clicked.connect(self._toggle_bridge)
        buttons.addWidget(self.connect_button)
        copy_button = QPushButton("Codex 설치 명령 복사")
        copy_button.clicked.connect(self._copy_setup_command)
        buttons.addWidget(copy_button)
        layout.addRow(buttons)
        self.bridge_label = QLabel("연결 대기")
        self.bridge_label.setWordWrap(True)
        layout.addRow(self.bridge_label)
        self.auto_run = QCheckBox("Codex 요청의 생성 코드를 자동 실행")
        self.auto_run.setToolTip("해제하면 QueryGIS 패널에서 생성 코드를 확인한 뒤 실행합니다")
        layout.addRow(self.auto_run)
        self.task_label = QLabel("작업 없음")
        self.task_label.setWordWrap(True)
        layout.addRow(self.task_label)
        actions = QHBoxLayout()
        self.approve_button = QPushButton("검토한 작업 실행")
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(self._approve)
        actions.addWidget(self.approve_button)
        self.cancel_button = QPushButton("작업 취소")
        self.cancel_button.clicked.connect(self._cancel_active)
        actions.addWidget(self.cancel_button)
        layout.addRow(actions)
        self.ui.mainLayout.insertWidget(2, controls)
        self._integration_ui = True

    def _provider_changed(self, *args):
        provider = self.provider_combo.currentData()
        defaults = {"openai": "gpt-5.5", "gemini": "", "backend": ""}
        settings = QSettings()
        self.model_input.setText(settings.value("QueryGISWithCodex/model/" + provider, defaults[provider]))
        self.backend_input.setVisible(provider == "backend")
        self.backend_label.setVisible(provider == "backend")
        # Existing Google account login is available only with the original backend.
        self.ui.btn_google_login.setVisible(provider == "backend")
        settings.setValue("QueryGISWithCodex/provider", provider)
        self.ui.line_apikey.setText("")
        self._session_key = ""

    def _config(self):
        if not self.ui:
            raise ValueError("QueryGIS 패널을 열어주세요")
        config = ProviderConfig(self.provider_combo.currentData(), self.model_input.text().strip(),
                                self.ui.line_apikey.text().strip(), self.backend_input.text().strip())
        if not config.api_key or not config.model:
            raise ValueError("QueryGIS 패널에서 API Key와 모델명을 입력하세요")
        self.save_api_key(config.api_key)
        settings = QSettings()
        settings.setValue("QueryGISWithCodex/model/" + config.provider, config.model)
        settings.setValue("QueryGISWithCodex/backend", config.backend_url)
        return config

    def _toggle_bridge(self):
        if self.bridge.running:
            self.bridge.stop()
            self.tasks.cancel_all()
            self.connect_button.setText("연결 시작")
            self.bridge_label.setText("연결 종료됨")
            return
        try:
            self._config()
            self._refresh_snapshot()
            self.bridge.start()
            self.connect_button.setText("연결 종료")
            self.bridge_label.setText("Codex 요청 접수 중 · API Key는 QueryGIS에만 보관")
        except Exception as exc:
            self.bridge_label.setText(str(exc))

    def _copy_setup_command(self):
        # This points to the development checkout, not the installed QGIS plugin.
        root = Path(QSettings().value("QueryGISWithCodex/repository", ""))
        if not (root / "scripts" / "setup.ps1").exists():
            selected = QFileDialog.getExistingDirectory(self.dockwidget, "QueryGIS_with_Codex 저장소 폴더 선택")
            if not selected:
                return
            root = Path(selected)
            if not (root / "scripts" / "setup.ps1").exists():
                self.bridge_label.setText("scripts/setup.ps1이 있는 저장소 폴더를 선택하세요")
                return
            QSettings().setValue("QueryGISWithCodex/repository", str(root))
        command = '& "' + str(root / "scripts" / "setup.ps1") + '"'
        QApplication.clipboard().setText(command)
        self.bridge_label.setText("설치 명령을 복사했습니다. PowerShell에서 한 번 실행하세요")

    def process_query(self):
        if not self.ui:
            return
        instruction = self.ui.text_query.toPlainText().strip()
        try:
            self._config()
            mode = "run" if self.ui.chk_ask_run.isChecked() else "ask"
            self.tasks.submit({"instruction": instruction, "request_id": uuid.uuid4().hex,
                               "mode": mode}, origin="panel")
            self.ui.text_query.clear()
        except ValueError as exc:
            self.ui.status_label.setText(str(exc))

    def add_chat_message(self, role, message):
        if role == "code-preview":
            widget = QWidget()
            layout = QVBoxLayout(widget)
            preview = QTextEdit()
            preview.setReadOnly(True)
            preview.setPlainText(message)
            preview.setMinimumHeight(160)
            layout.addWidget(preview)
            return widget
        widget = super().add_chat_message(role, message)
        for label in widget.findChildren(QLabel):
            label.setTextFormat(Qt.PlainText)
        return widget

    def _refresh_snapshot(self):
        configured = bool(self.ui and self.ui.line_apikey.text().strip() and self.model_input.text().strip())
        layers = [{"id": layer.id(), "name": layer.name(), "crs": layer.crs().authid(),
                   "type": "vector" if isinstance(layer, QgsVectorLayer) else "raster"}
                  for layer in QgsProject.instance().mapLayers().values()]
        self.bridge.set_snapshot({"provider_configured": configured, "layers": layers,
                                  "project_crs": QgsProject.instance().crs().authid()})

    def _context(self, layer_ids):
        project = QgsProject.instance()
        if layer_ids:
            layers = [project.mapLayer(i) for i in layer_ids]
            if any(layer is None for layer in layers):
                raise ValueError("요청한 레이어가 현재 프로젝트에 없습니다. 레이어 목록을 다시 확인하세요")
        else:
            layers = list(project.mapLayers().values())
        result = []
        for layer in layers:
            info = {"id": layer.id(), "name": layer.name(), "crs": layer.crs().authid(),
                    "type": "vector" if isinstance(layer, QgsVectorLayer) else "raster"}
            if isinstance(layer, QgsVectorLayer):
                info.update(fields=[{"name": f.name(), "type": f.typeName()} for f in layer.fields()],
                            geometry=core.QgsWkbTypes.displayString(layer.wkbType()),
                            feature_count=layer.featureCount(),
                            feature_samples=self._collect_vector_feature_rows(layer, max_rows=3))
            elif isinstance(layer, QgsRasterLayer):
                info.update(band_count=layer.bandCount(), width=layer.width(), height=layer.height())
            extent = layer.extent()
            info["extent"] = [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()]
            result.append(info)
        return {"project": {"crs": project.crs().authid(), "title": project.title()}, "layers": result}

    def _tick(self):
        if self._closing or not self.ui or not self._integration_ui:
            return
        self._refresh_snapshot()
        if self._active_task:
            status = self.tasks.public(self._active_task)
            self.task_label.setText(status["state"] + " · " + status["message"])
            self.approve_button.setEnabled(status["state"] == "awaiting_approval")
            if status["state"] in TERMINAL and not (self._plan_worker and self._plan_worker.isRunning()):
                self._active_task = None
            return
        if self._plan_worker and self._plan_worker.isRunning():
            return
        task_id = self.tasks.next_queued()
        if task_id:
            self._active_task = task_id
            self._correction_count = 0
            task = self.tasks.details(task_id)
            try:
                self._task_config = self._config()
                self._task_context = self._context(task["payload"]["layer_ids"])
                self.append_chat_message("user", "[" + task["origin"] + "] " + task["payload"]["instruction"])
                self._start_plan(task_id)
            except Exception as exc:
                self._fail(task_id, str(exc))

    def _start_plan(self, task_id, correction=None):
        if not self.tasks.update(task_id, "planning", "QueryGIS가 분석 방법과 실행 코드를 생성 중"):
            return
        self._plan_worker = PlanWorker(task_id, self._task_config, self.tasks.details(task_id)["payload"],
                                       self._task_context, correction)
        self._plan_worker.planned.connect(self._on_plan)
        self._plan_worker.failed.connect(self._fail)
        self._plan_worker.start()

    def _on_plan(self, task_id, plan):
        if self._closing or self.tasks.public(task_id)["state"] != "planning":
            return
        self._plan = plan
        if not self.ui:
            self.tasks.cancel(task_id)
            return
        self.append_chat_message("assistant-print", plan["message"])
        if not plan["code"].strip():
            self.tasks.update(task_id, "succeeded", "QueryGIS 답변 완료",
                              {"message": plan["message"], "layers": [], "stdout": ""})
            return
        # Render a non-runnable preview. The task button below preserves lifecycle tracking.
        self.append_chat_message("code-preview", plan["code"])
        origin = self.tasks.details(task_id)["origin"]
        if self._correction_count == 0 and (origin == "panel" or self.auto_run.isChecked()):
            self._execute(task_id)
        else:
            self.tasks.update(task_id, "awaiting_approval", "QGIS 패널에서 생성 코드를 검토한 뒤 실행하세요")
            self.approve_button.setEnabled(True)

    def _approve(self):
        if self._active_task and self.tasks.public(self._active_task)["state"] == "awaiting_approval":
            self._execute(self._active_task)

    def _cancel_active(self):
        if self._active_task:
            self.tasks.cancel(self._active_task)

    def _execute(self, task_id):
        if not self.tasks.update(task_id, "running", "QueryGIS가 QGIS에서 작업을 실행 중"):
            return
        self.approve_button.setEnabled(False)
        task = self.tasks.details(task_id)
        code = self._plan["code"]
        try:
            result = self._execute_python(code, task["cancel_event"])
            result["message"] = self._plan["message"]
            state = "cancelled" if task["cancel_event"].is_set() else "succeeded"
            self.tasks.update(task_id, state, "작업 취소됨" if state == "cancelled" else "QueryGIS 실행 완료", result)
            self.append_chat_message("assistant-print", result["stdout"] or "실행 완료")
        except Exception:
            error = traceback.format_exc().replace(self._task_config.api_key, "[REDACTED]")[-12000:]
            if task["cancel_event"].is_set():
                self.tasks.update(task_id, "cancelled", "실행 중 취소됨", {"error": error})
            else:
                self.append_chat_message("assistant-print", error)
                if self._correction_count == 0:
                    self._correction_count += 1
                    self.append_chat_message("assistant-print", "QueryGIS가 수정안을 생성합니다. 이전 실행이 일부 반영되었을 수 있으므로 수정안은 검토 후 실행하세요.")
                    self._start_plan(task_id, {"error": error, "code": code})
                else:
                    self._fail(task_id, error)

    def _execute_python(self, code, cancel_event):
        import processing
        project = QgsProject.instance()
        before = set(project.mapLayers())
        feedback = TaskFeedback(cancel_event)
        original_run = processing.run

        def run_with_feedback(*args, **kwargs):
            if cancel_event.is_set():
                raise RuntimeError("작업이 취소되었습니다")
            if len(args) < 4 and "feedback" not in kwargs:
                kwargs["feedback"] = feedback
            return original_run(*args, **kwargs)

        scope = {name: getattr(core, name) for name in dir(core) if name.startswith("Qgs") or name == "Qgis"}
        scope.update({"__builtins__": builtins.__dict__, "__name__": "__querygis_task__",
                      "iface": self.iface, "processing": processing, "os": os,
                      "find_layer_by_keyword": self.find_layer_by_keyword, "get_layer_safe": self.get_layer_safe})
        output = io.StringIO()
        processing.run = run_with_feedback
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                exec(compile(code, "<QueryGIS task>", "exec"), scope)
        finally:
            processing.run = original_run
        layers = []
        for layer_id in set(project.mapLayers()) - before:
            layer = project.mapLayer(layer_id)
            if not layer.isValid():
                raise RuntimeError("결과 레이어가 유효하지 않습니다: " + layer.name())
            item = {"id": layer_id, "name": layer.name(), "crs": layer.crs().authid()}
            if isinstance(layer, QgsVectorLayer):
                item["feature_count"] = layer.featureCount()
            layers.append(item)
        return {"layers": layers, "stdout": output.getvalue()[-20000:]}

    def _fail(self, task_id, error):
        if self._closing:
            return
        self.tasks.update(task_id, "failed", "QueryGIS 작업 실패", {"error": error})
        if self.ui:
            self.append_chat_message("assistant-print", error)

    def unload(self):
        self._closing = True
        self.timer.stop()
        self.tasks.cancel_all()
        self.bridge.stop()
        if self._plan_worker and self._plan_worker.isRunning():
            # Network worker owns immutable inputs only; never terminate a thread unsafely.
            self._plan_worker.planned.disconnect()
            self._plan_worker.failed.disconnect()
            self._plan_worker.finished.connect(self._plan_worker.deleteLater)
            _RETIRED_WORKERS.append(self._plan_worker)
            self._plan_worker.finished.connect(lambda: _release_workers())
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        super().unload()


_RETIRED_WORKERS = []


def _release_workers():
    _RETIRED_WORKERS[:] = [worker for worker in _RETIRED_WORKERS if worker.isRunning()]
