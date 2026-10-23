"""Real Qt widgets/signals with a QGIS stub. Does not claim spatial-analysis validation."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qgis_plugin"))
from qgis_stub import install, Interface, Project, VectorLayer
install()
from PyQt5.QtCore import QSettings, QCoreApplication, QThread
from PyQt5.QtWidgets import QApplication
from querygis_with_codex.plugin import QueryGISWithCodex
from codex_mcp.client import QueryGISClient


class QtLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, cls.settings_dir.name)
        QCoreApplication.setOrganizationName("QueryGISCodexTests")
        QCoreApplication.setApplicationName("QueryGISCodexTests")

    @classmethod
    def tearDownClass(cls):
        cls.settings_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, QUERYGIS_CONNECTION_FILE=str(Path(self.temp.name) / "connection.json"))
        self.env.start()
        Project.instance().layers.clear()
        Project.instance().execution_threads.clear()
        self.iface = Interface()
        self.plugin = QueryGISWithCodex(self.iface)
        self.plugin.initGui()
        self.plugin.run()
        self.plugin.ui.line_apikey.setText("test-key-only")
        self.plugin.model_input.setText("test-model")

    def tearDown(self):
        self.plugin.unload()
        self.app.processEvents()
        self.iface.window.close()
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def until(self, predicate, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Qt task did not reach expected state")

    def test_panel_task_executes_on_main_thread(self):
        code = "QgsProject.instance().addMapLayer(QgsVectorLayer('Point', 'buffer', 'memory'))\nprint('done')"
        with patch("querygis_with_codex.plugin.generate_plan", return_value={"message": "계획", "code": code}):
            self.plugin.ui.text_query.setPlainText("학교 주변 500m 버퍼")
            self.plugin.process_query()
            self.until(lambda: len(Project.instance().layers) == 1)
        self.assertEqual(Project.instance().execution_threads, [self.app.thread()])
        self.assertEqual(self.plugin.tasks.public(self.plugin._active_task)["state"], "succeeded")

    def test_codex_task_requires_panel_review_by_default(self):
        self.plugin._toggle_bridge()
        client = QueryGISClient()
        code = "QgsProject.instance().addMapLayer(QgsVectorLayer('Point', 'reviewed', 'memory'))"
        with patch("querygis_with_codex.plugin.generate_plan", return_value={"message": "검토", "code": code}):
            task = client.request("POST", "/tasks", {"instruction": "buffer", "request_id": "review"})
            self.until(lambda: self.plugin.tasks.public(task["id"])["state"] == "awaiting_approval")
            self.assertEqual(len(Project.instance().layers), 0)
            self.plugin._approve()
            self.assertEqual(client.request("GET", client.task_path(task["id"]))["state"], "succeeded")
        self.assertNotIn("test-key-only", self.plugin.bridge.discovery_file.read_text())

    def test_codex_auto_run_and_correction_review(self):
        self.plugin.auto_run.setChecked(True)
        plans = [{"message": "first", "code": "raise ValueError('example failure')"},
                 {"message": "corrected", "code": "print('fixed')"}]
        with patch("querygis_with_codex.plugin.generate_plan", side_effect=plans):
            task = self.plugin.tasks.submit({"instruction": "buffer", "request_id": "fix"})
            self.until(lambda: self.plugin.tasks.public(task["id"])["state"] == "awaiting_approval")
            self.plugin._approve()
            self.assertEqual(self.plugin.tasks.public(task["id"])["state"], "succeeded")

    def test_invalid_layer_never_calls_ai(self):
        with patch("querygis_with_codex.plugin.generate_plan") as generate:
            task = self.plugin.tasks.submit({"instruction": "buffer", "request_id": "missing", "layer_ids": ["missing"]})
            self.until(lambda: self.plugin.tasks.public(task["id"])["state"] == "failed")
            generate.assert_not_called()

    def test_failed_execution_restores_processing_function(self):
        import threading
        import processing
        original = processing.run
        with self.assertRaises(ValueError):
            self.plugin._execute_python("raise ValueError('fail')", threading.Event())
        self.assertIs(processing.run, original)

    def test_panel_api_key_not_written_to_settings(self):
        self.plugin._config()
        settings = QSettings()
        self.assertFalse(any("api_key" in key.lower() for key in settings.allKeys()))


if __name__ == "__main__":
    unittest.main()
