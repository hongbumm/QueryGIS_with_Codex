"""Forward goals to an installed QueryGIS instance. No AI or GIS implementation."""
import json

from .tasks import TERMINAL


def response_error(text):
    """The existing /chat contract reports some auth failures with HTTP 200."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    output = data.get("output", "")
    message = output.get("text", "") if isinstance(output, dict) else str(output)
    if data.get("error"):
        return message or str(data["error"])
    lower = message.lower()
    if "invalid api key" in lower or ("key" in lower and "deprecated" in lower):
        return message
    return None


class ExistingQueryGISAdapter:
    REQUIRED = ("run", "process_query", "handle_response", "handle_error", "run_code_string",
                "append_chat_message", "_start_backend_attempt", "_parse_backend_response", "stop_wave_progress")
    HOOKS = ("handle_response", "handle_error", "run_code_string", "append_chat_message", "_start_backend_attempt")

    def __init__(self, target, store, project):
        if not all(callable(getattr(target, name, None)) for name in self.REQUIRED):
            raise ValueError("지원하는 기존 QueryGIS 플러그인을 찾지 못했습니다")
        self.target, self.store, self.project = target, store, project
        self._originals, self._hooks = {}, {}
        self.active = None
        self._generation = 0
        self._waiting = self._settle = False
        self._execution_success = self._error = None
        self._messages = []
        self._secret = ""
        self._before_layers = set()
        self._locked = []
        self._closing = False

    @property
    def ready(self):
        ui = getattr(self.target, "ui", None)
        return bool(ui and (ui.line_apikey.text().strip() or getattr(self.target, "user_oauth_sub", None)))

    def attach(self):
        if self._originals:
            return
        for name in self.HOOKS:
            self._originals[name] = getattr(self.target, name)
            self._hooks[name] = getattr(self, "_" + name.lstrip("_"))
            setattr(self.target, name, self._hooks[name])

    def detach(self):
        self._closing = True
        self.store.cancel_all()
        self._restore_ui()
        for name, original in self._originals.items():
            if getattr(self.target, name) is self._hooks[name]:
                setattr(self.target, name, original)
        # An existing worker can still hold a wrapper; retain its original delegates.

    def _redact(self, text):
        text = str(text)
        return text.replace(self._secret, "[REDACTED]") if self._secret else text

    def _cancelled(self):
        return bool(self.active and self.store.details(self.active)["cancel_event"].is_set())

    def _worker_running(self):
        worker = getattr(self.target, "worker", None)
        return bool(worker and worker.isRunning())

    def poll(self):
        if self._closing:
            return
        if self.active:
            if not getattr(self.target, "ui", None):
                self.store.cancel(self.active)
            if self._worker_running():
                return
            if self._cancelled() or self._settle:
                self._finish()
            return
        if self._worker_running() or not self.ready or not self.target.ui.btn_ask.isEnabled():
            return
        task_id = self.store.next_queued()
        if task_id:
            self._begin(task_id)

    def _begin(self, task_id):
        self.active = task_id
        self._waiting = self._settle = False
        self._execution_success = self._error = None
        self._messages = []
        ui = self.target.ui
        self._secret = ui.line_apikey.text().strip()
        self._before_layers = set(self.project.mapLayers())
        task = self.store.details(task_id)["payload"]
        self.store.update(task_id, "planning", "기존 QueryGIS에 작업 전달 중")
        draft, checked = ui.text_query.toPlainText(), ui.chk_ask_run.isChecked()
        generation = self._generation
        for name in ("text_query", "chk_ask_run", "btn_ask", "chatWidget"):
            widget = getattr(ui, name, None)
            if widget is not None:
                self._locked.append((widget, widget.isEnabled()))
                widget.setEnabled(False)
        try:
            ui.text_query.setPlainText(task["instruction"])
            ui.chk_ask_run.setChecked(task["mode"] == "run")
            # Existing QueryGIS owns the service key, endpoint, payload and AI flow.
            self.target.process_query()
            if self._generation == generation and not self._waiting:
                self._error = "기존 QueryGIS가 요청을 시작하지 못했습니다. 패널의 인증과 상태를 확인하세요"
                self._settle = True
        except Exception as exc:
            self._error = self._redact(exc)
            self._settle = True
        finally:
            if getattr(self.target, "ui", None) is ui:
                ui.text_query.setPlainText(draft)
                ui.chk_ask_run.setChecked(checked)

    def _start_backend_attempt(self, *args, **kwargs):
        if self.active and (self._closing or self._cancelled()):
            self._waiting, self._settle = False, True
            return
        if self.active:
            self._generation += 1
            self._waiting, self._settle = True, False
            self.store.update(self.active, "planning", "기존 QueryGIS 서버에서 요청 처리 중")
        return self._originals["_start_backend_attempt"](*args, **kwargs)

    def _handle_response(self, text):
        if self.active and (self._closing or self._cancelled() or not getattr(self.target, "ui", None)):
            self._waiting, self._settle = False, True
            return
        if not self.active:
            return self._originals["handle_response"](text)
        generation = self._generation
        self._waiting = False
        error = response_error(text)
        try:
            if error:
                self._handle_error(error)
            else:
                # Preserve original tool_followup, full-RAG retries and /fix-code.
                self._originals["handle_response"](text)
        except Exception as exc:
            self._handle_error(str(exc))
        finally:
            if self._generation == generation:
                self._settle = True

    def _handle_error(self, error):
        if self.active:
            self._error = self._redact(error)
            self._waiting, self._settle = False, True
        if not self._closing:
            return self._originals["handle_error"](self._redact(error))

    def _run_code_string(self, code):
        if self.active and (self._closing or self._cancelled()):
            return False
        if self.active:
            self.store.update(self.active, "running", "기존 QueryGIS가 QGIS에서 실행 중")
        try:
            result = self._originals["run_code_string"](code)
        except Exception as exc:
            if self.active:
                self._error = self._redact(exc)
            raise
        if self.active:
            self._execution_success = bool(result)
        return result

    def _append_chat_message(self, role, message):
        if self.active and role == "assistant-print":
            self._messages.append(self._redact(message))
        return self._originals["append_chat_message"](role, message)

    def _restore_ui(self):
        for widget, enabled in self._locked:
            try:
                widget.setEnabled(enabled)
            except RuntimeError:
                pass
        self._locked.clear()

    def _finish(self):
        task_id = self.active
        layers = []
        for layer_id in set(self.project.mapLayers()) - self._before_layers:
            layer = self.project.mapLayer(layer_id)
            item = {"id": layer_id, "name": layer.name(), "valid": layer.isValid(), "crs": layer.crs().authid()}
            if hasattr(layer, "featureCount"):
                item["feature_count"] = layer.featureCount()
            layers.append(item)
        if self._cancelled():
            state, message = "cancelled", "취소됨. 이미 실행된 QGIS 변경은 유지될 수 있습니다"
        elif self._error or self._execution_success is False or any(not layer["valid"] for layer in layers):
            state, message = "failed", "기존 QueryGIS에서 작업이 실패했습니다"
        else:
            state, message = "succeeded", "기존 QueryGIS 작업 완료"
        result = {"executed": self._execution_success is True, "layers": layers,
                  "message": "\n".join(self._messages)[-16000:] or (
                      "QueryGIS 패널에 답변을 표시했습니다" if self._execution_success is None else message)}
        if self._error:
            result["error"] = self._error
        elif self._execution_success is False:
            result["error"] = self._redact(getattr(self.target, "_last_execution_error_message", "QueryGIS execution failed"))
        if self.store.public(task_id)["state"] not in TERMINAL:
            self.store.update(task_id, state, message, result)
        self._restore_ui()
        if getattr(self.target, "ui", None):
            self.target.stop_wave_progress("Cancelled" if state == "cancelled" else "Finished")
            self.target.ui.btn_ask.setEnabled(True)
        self.active, self._secret = None, ""
