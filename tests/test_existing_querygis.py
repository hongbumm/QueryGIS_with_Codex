"""Real Qt inputs, with controlled installed-QueryGIS and project test doubles."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qgis_plugin"))
from qgis_stub import install, Project, VectorLayer
install()
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread
from legacy_stub import ExistingQueryGIS
from querygis_codex_connector.adapter import ExistingQueryGISAdapter
from querygis_codex_connector.tasks import TaskStore
from querygis_codex_connector.connector import QueryGISCodexConnector

CODE = {"output": {"text": "```python\nserver_generated_code\n```"}}


class ExistingQueryGISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.project = Project.instance()
        self.project.layers.clear()
        self.store = TaskStore()
        self.target = ExistingQueryGIS()
        self.original_process = self.target.process_query
        self.original_response = self.target.handle_response
        self.adapter = ExistingQueryGISAdapter(self.target, self.store, self.project)
        self.adapter.attach()

    def tearDown(self):
        self.adapter.detach()

    def submit(self, mode="run"):
        task = self.store.submit({"instruction": "학교 주변 500m 버퍼", "request_id": "request-1", "mode": mode})
        self.adapter.poll()
        return task["id"]

    def test_existing_request_path_and_service_key_are_used(self):
        task = self.submit()
        self.assertEqual(self.target.requests[0]["instruction"], "학교 주변 500m 버퍼")
        self.assertEqual(self.target.requests[0]["api_key"], "querygis-issued-service-key")
        self.assertEqual(self.target.requests[0]["mode"], "instruction_only")
        self.assertEqual(self.target.process_query, self.original_process)
        self.assertNotIn("querygis-issued-service-key", str(self.store.public(task)))

    def test_execution_is_delegated_and_new_layers_are_reported(self):
        execution_threads = []
        def execute(code):
            execution_threads.append(QThread.currentThread())
            self.project.addMapLayer(VectorLayer(name="buffer"))
            self.target.append_chat_message("assistant-print", "buffer created")
            return True
        self.target.execute_action = execute
        task = self.submit()
        self.target.reply(CODE)
        self.adapter.poll()
        result = self.store.public(task)
        self.assertEqual(result["state"], "succeeded")
        self.assertTrue(result["result"]["executed"])
        self.assertEqual(result["result"]["layers"][0]["name"], "buffer")
        self.assertEqual(execution_threads, [self.app.thread()])

    def test_user_draft_and_checkbox_are_preserved(self):
        self.target.ui.text_query.setPlainText("사용자가 작성하던 문장")
        self.target.ui.chk_ask_run.setChecked(False)
        task = self.submit()
        self.assertEqual(self.target.ui.text_query.toPlainText(), "사용자가 작성하던 문장")
        self.assertFalse(self.target.ui.chk_ask_run.isChecked())
        self.assertFalse(self.target.ui.text_query.isEnabled())
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertTrue(self.target.ui.text_query.isEnabled())

    def test_ask_prepares_original_response_without_execution(self):
        task = self.submit(mode="ask")
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertEqual(self.target.executions, [])
        self.assertEqual(self.store.public(task)["state"], "succeeded")
        self.assertFalse(self.store.public(task)["result"]["executed"])

    def test_flask_tool_followup_stays_owned_by_querygis(self):
        task = self.submit()
        self.target.reply({"tool_request": {"tools": [{"name": "context_full"}]}})
        self.adapter.poll()
        self.assertEqual(self.store.public(task)["state"], "planning")
        self.assertEqual(self.target.requests[-1]["mode"], "tool_followup")
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertEqual(self.store.public(task)["state"], "succeeded")

    def test_existing_rag_retry_is_not_prematurely_completed(self):
        self.target.execute_action = lambda code: False
        task = self.submit()
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertEqual(self.store.public(task)["state"], "planning")
        self.assertEqual(self.target.requests[-1]["mode"], "rag_full")
        self.target.execute_action = lambda code: True
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertEqual(self.store.public(task)["state"], "succeeded")

    def test_invalid_querygis_key_is_a_failure_not_success(self):
        task = self.submit()
        self.target.reply({"output": "Invalid API key."})
        self.adapter.poll()
        self.assertEqual(self.store.public(task)["state"], "failed")
        self.assertEqual(self.target.executions, [])

    def test_pending_cancel_suppresses_late_server_code(self):
        task = self.submit()
        self.store.cancel(task)
        self.target.reply(CODE)
        self.adapter.poll()
        self.assertEqual(self.target.executions, [])
        self.assertEqual(self.store.public(task)["state"], "cancelled")

    def test_running_cancel_reports_existing_changes(self):
        task = self.submit()
        def execute(code):
            self.store.cancel(task)
            self.project.addMapLayer(VectorLayer(name="already-created"))
            return True
        self.target.execute_action = execute
        self.target.reply(CODE)
        self.adapter.poll()
        result = self.store.public(task)
        self.assertEqual(result["state"], "cancelled")
        self.assertTrue(result["result"]["executed"])
        self.assertEqual(len(result["result"]["layers"]), 1)

    def test_existing_manual_request_finishes_before_dispatch(self):
        self.target.worker.isRunning = lambda: True
        task = self.submit()
        self.assertEqual(self.target.requests, [])
        self.assertEqual(self.store.public(task)["state"], "queued")

    def test_methods_restored_on_disconnect(self):
        self.adapter.detach()
        self.assertEqual(self.target.handle_response, self.original_response)
        self.assertEqual(self.target.process_query, self.original_process)

    def test_detach_pending_request_cannot_execute_late_response(self):
        task = self.submit()
        self.adapter.detach()
        self.target.reply(CODE)
        self.assertEqual(self.target.executions, [])

    def test_connector_uses_installed_querygis_and_can_connect_before_key_entry(self):
        import tempfile
        from unittest.mock import patch
        from qgis_stub import Interface
        from qgis.utils import plugins
        self.adapter.detach()
        self.target.ui.line_apikey.clear()
        plugins["QueryGIS_Local"] = ExistingQueryGIS()
        plugins["query_gis"] = self.target
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, QUERYGIS_CONNECTION_FILE=str(Path(temporary) / "connection.json")):
                connector = QueryGISCodexConnector(Interface())
                connector.initGui()
                try:
                    connector.toggle()
                    self.assertTrue(connector.bridge.running)
                    self.assertFalse(connector.bridge.snapshot()["querygis_ready"])
                    self.assertIs(connector.adapter.target, self.target)
                finally:
                    connector.unload()
        plugins.clear()


if __name__ == "__main__":
    unittest.main()
