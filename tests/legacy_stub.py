"""A controllable existing-QueryGIS boundary; not a substitute for QGIS spatial tests."""
import json
import re
from types import SimpleNamespace
from PyQt5.QtWidgets import QWidget, QTextEdit, QCheckBox, QLineEdit, QPushButton


class ExistingQueryGIS:
    def __init__(self):
        self.ui = SimpleNamespace(text_query=QTextEdit(), chk_ask_run=QCheckBox(),
            line_apikey=QLineEdit(), btn_ask=QPushButton(), chatWidget=QWidget())
        self.ui.line_apikey.setText("querygis-issued-service-key")
        self.ui.chk_ask_run.setChecked(True)
        self.worker = SimpleNamespace(isRunning=lambda: False)
        self.requests, self.executions, self.messages = [], [], []
        self.user_oauth_sub = None
        self.execute_action = lambda code: True
        self._last_execution_error_message = "Example QueryGIS execution error"

    def run(self): pass

    def process_query(self):
        self._instruction = self.ui.text_query.toPlainText()
        self._should_run = self.ui.chk_ask_run.isChecked()
        self._start_backend_attempt("instruction_only")
        self.ui.text_query.clear()

    def _start_backend_attempt(self, mode, **kwargs):
        self.requests.append({"mode": mode, "instruction": self._instruction,
            "api_key": self.ui.line_apikey.text(), **kwargs})
        self.worker = SimpleNamespace(isRunning=lambda: True)
        self.response_handler = self.handle_response

    def reply(self, payload):
        self.worker = SimpleNamespace(isRunning=lambda: False)
        self.response_handler(json.dumps(payload))

    def _parse_backend_response(self, text):
        data = json.loads(text)
        output = data.get("output", {})
        display = output.get("text", "") if isinstance(output, dict) else str(output)
        return display, re.findall(r"```python\n([\s\S]*?)```", display)

    def handle_response(self, text):
        data = json.loads(text)
        if data.get("tool_request"):
            self._start_backend_attempt("tool_followup", tool_data={"owned_by": "existing_querygis"})
            return
        display, codes = self._parse_backend_response(text)
        if codes and self._should_run:
            if not self.run_code_string(codes[-1]):
                if len(self.requests) == 1:
                    self._start_backend_attempt("rag_full", error_message="existing error")
                    return
        else:
            self.append_chat_message("assistant-print", display if not codes else "Code prepared in QueryGIS")
        self.ui.btn_ask.setEnabled(True)

    def run_code_string(self, code):
        self.executions.append(code)
        return self.execute_action(code)

    def handle_error(self, message):
        self.append_chat_message("assistant-print", message)

    def append_chat_message(self, role, message):
        self.messages.append((role, message))

    def stop_wave_progress(self, message): pass
