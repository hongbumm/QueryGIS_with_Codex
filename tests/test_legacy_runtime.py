"""Optional: actual original QueryGIS Python code, Qt/QGIS test doubles and HTTP fixture.

QUERYGIS_LEGACY_PLUGIN selects a local original plugin checkout. No original file is edited.
This exercises the real request/correction code, but not actual QGIS geometry processing.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import importlib.util
import json
import sys
import threading
import tempfile
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "qgis_plugin"))
from querygis_codex_connector.adapter import ExistingQueryGISAdapter
from querygis_codex_connector.tasks import TaskStore

LEGACY = os.environ.get("QUERYGIS_LEGACY_PLUGIN")


@unittest.skipUnless(LEGACY, "Set QUERYGIS_LEGACY_PLUGIN to exercise an original QueryGIS checkout")
class ActualLegacyRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qgis_stub import install
        install()
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QSettings, QCoreApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, cls.settings_dir.name)
        QCoreApplication.setOrganizationName("QueryGISConnectorRuntimeTests")
        QCoreApplication.setApplicationName("QueryGISConnectorRuntimeTests")
        path = Path(LEGACY)
        package = types.ModuleType("_querygis_legacy_fixture")
        package.__path__ = [str(path)]
        sys.modules[package.__name__] = package
        spec = importlib.util.spec_from_file_location(package.__name__ + ".query_gis", path / "query_gis.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        cls.settings_dir.cleanup()

    def setUp(self):
        from qgis_stub import Interface, Project
        self.iface = Interface()
        self.target = self.module.QueryGIS(self.iface)
        self.target.run()
        self.target.ui.line_apikey.setText("fixture-querygis-service-key")
        self.store = TaskStore()
        self.adapter = ExistingQueryGISAdapter(self.target, self.store, Project.instance())
        self.adapter.attach()
        self.requests = []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body))
                if self.path == "/fix-code":
                    reply = {"output": {"text": "print('Done! corrected by existing QueryGIS')"}, "fixed": True}
                elif body["user_input"] == "fix this":
                    reply = {"output": {"text": "```python\nraise ValueError('fixture error')\n```"}}
                else:
                    reply = {"output": {"text": "```python\nprint('Done! original QueryGIS executed')\n```"}}
                encoded = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        base = "http://127.0.0.1:%d" % self.server.server_port
        worker = self.module.BackendWorker
        class FixtureWorker(worker):
            def __init__(self, payload, backend_url=None, timeout_sec=120):
                super().__init__(payload, base + "/chat", timeout_sec=5)
        self.worker_patch = patch.object(self.module, "BackendWorker", FixtureWorker)
        self.worker_patch.start()
        real_request = self.module.requests.sessions.Session.request
        def fixture_request(session, method, url, *args, **kwargs):
            from urllib.parse import urlsplit
            path = urlsplit(url).path
            if path not in {"/chat", "/fix-code"}:
                raise AssertionError("Unexpected original QueryGIS network path: " + path)
            url = base + path
            kwargs["timeout"] = 5
            return real_request(session, method, url, *args, **kwargs)
        self.post_patch = patch.object(self.module.requests.sessions.Session, "request", fixture_request)
        self.post_patch.start()
        self.report_patch = patch.object(self.module, "_send_error_report", lambda *args, **kwargs: None)
        self.report_patch.start()

    def tearDown(self):
        self.adapter.detach()
        self.target.unload()
        self.worker_patch.stop()
        self.post_patch.stop()
        self.report_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.app.processEvents()

    def exercise(self, instruction):
        task = self.store.submit({"instruction": instruction, "request_id": "original-runtime"})
        end = time.monotonic() + 15
        while time.monotonic() < end:
            self.app.processEvents()
            self.adapter.poll()
            if self.store.public(task["id"])["state"] in {"succeeded", "failed"}:
                return self.store.public(task["id"])
            time.sleep(0.01)
        self.fail("Original QueryGIS request did not complete")

    def test_actual_original_chat_and_execution(self):
        result = self.exercise("describe this")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertTrue(result["result"]["executed"])
        self.assertEqual(self.requests[0][0], "/chat")
        self.assertEqual(self.requests[0][1]["api_key"], "fixture-querygis-service-key")
        self.assertNotIn("fixture-querygis-service-key", str(result))

    def test_actual_original_fix_code_flow(self):
        result = self.exercise("fix this")
        self.assertEqual(result["state"], "succeeded", result)
        self.assertTrue(any(path == "/fix-code" for path, payload in self.requests))
        fixed_payload = next(payload for path, payload in self.requests if path == "/fix-code")
        self.assertEqual(fixed_payload["api_key"], "fixture-querygis-service-key")
        self.assertIn("broken_code", fixed_payload)
