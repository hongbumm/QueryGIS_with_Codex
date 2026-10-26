"""Real loopback/MCP protocol tests; no paid API or QGIS operation is invoked."""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins" / "querygis" / "server"
sys.path.insert(0, str(ROOT / "qgis_plugin"))
sys.path.insert(0, str(SERVER))
from querygis_codex_connector.tasks import TaskStore
from querygis_codex_connector.bridge import BridgeServer
from querygis_codex_connector.adapter import response_error
from client import QueryGISClient


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.payload = {"instruction": "선택한 학교 레이어 주변 500m 버퍼", "request_id": "request-1"}

    def test_uncertain_delivery_does_not_duplicate_work(self):
        task = self.store.submit(self.payload)
        self.assertEqual(task["id"], self.store.submit(self.payload)["id"])
        self.store.update(task["id"], "planning", "planning")
        self.store.update(task["id"], "running", "running")
        self.store.update(task["id"], "succeeded", "done", {"executed": True})
        self.assertEqual(self.store.submit(self.payload)["state"], "succeeded")
        with self.assertRaises(ValueError):
            self.store.submit({**self.payload, "instruction": "different"})

    def test_only_task_controls_are_accepted(self):
        for field in ("api_key", "code", "python", "model", "provider", "server_url", "layer_ids"):
            with self.assertRaises(ValueError):
                self.store.submit({**self.payload, field: "unsupported"})

    def test_cancelled_request_cannot_execute_late_response(self):
        task = self.store.submit(self.payload)
        self.store.update(task["id"], "planning", "planning")
        self.store.cancel(task["id"])
        self.assertFalse(self.store.update(task["id"], "running", "late response"))

    def test_running_cancel_does_not_claim_immediate_interruption(self):
        task = self.store.submit(self.payload)
        self.store.update(task["id"], "planning", "planning")
        self.store.update(task["id"], "running", "running")
        result = self.store.cancel(task["id"])
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["cancel_requested"])

    def test_bad_task_parameters(self):
        for payload in ([], {"instruction": "buffer"}, {**self.payload, "instruction": " "},
                        {**self.payload, "mode": "execute-code"}):
            with self.assertRaises(ValueError):
                self.store.submit(payload)


class ServiceAuthTests(unittest.TestCase):
    def test_existing_flask_http_200_auth_errors_are_failures(self):
        for response in ({"output": "Invalid API key."},
                         {"output": "You're Key is Deprecated. Please Contact 3DLabs."},
                         {"output": {"text": "Usage limit reached"}, "error": "subscription_required"}):
            self.assertTrue(response_error(json.dumps(response)))

    def test_existing_success_and_tool_requests_are_not_auth_errors(self):
        for response in ("plain text", '{"output":{"text":"answer"}}',
                         '{"tool_request":{"tools":[{"name":"context_full"}]}}'):
            self.assertIsNone(response_error(response))


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "connection.json"
        self.store = TaskStore()
        self.bridge = BridgeServer(self.store, self.path)
        self.bridge.set_snapshot({"querygis_ready": True, "layers": [{"id": "schools", "name": "학교"}]})
        self.bridge.start()
        self.client = QueryGISClient(self.path)

    def tearDown(self):
        self.bridge.stop()
        self.temporary.cleanup()

    def test_round_trip_has_no_credentials_or_code(self):
        self.assertTrue(self.client.status()["connected"])
        task = self.client.request("POST", "/tasks", {"instruction": "500m 버퍼", "request_id": "roundtrip"})
        self.store.update(task["id"], "planning", "QueryGIS request")
        self.store.update(task["id"], "running", "QueryGIS executing")
        self.store.update(task["id"], "succeeded", "done", {"executed": True, "layers": [{"id": "buffer"}]})
        outcome = self.client.request("GET", self.client.task_path(task["id"]))
        self.assertTrue(outcome["result"]["executed"])
        self.assertNotIn("payload", outcome)
        self.assertNotIn("api_key", outcome)
        self.assertNotIn("token", outcome)

    def test_browser_origin_and_missing_token_are_rejected(self):
        data = json.loads(self.path.read_text())
        url = "http://127.0.0.1:%d/health" % data["port"]
        for headers in ({}, {"Authorization": "Bearer " + data["token"], "Origin": "https://example.com"}):
            with self.assertRaises(HTTPError) as caught:
                build_opener(ProxyHandler({})).open(Request(url, headers=headers), timeout=3)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()

    def test_connection_check_works_without_a_service_key(self):
        self.bridge.set_snapshot({"querygis_ready": False})
        self.assertTrue(self.client.status()["connected"])
        with self.assertRaisesRegex(RuntimeError, "QueryGIS 발급 Key"):
            self.client.request("POST", "/tasks", {"instruction": "buffer", "request_id": "no-key"})

    def test_second_session_does_not_replace_active_connection(self):
        with self.assertRaises(RuntimeError):
            BridgeServer(TaskStore(), self.path).start()
        self.assertTrue(self.client.status()["connected"])

    def test_cancel_shutdown_and_no_execution_route(self):
        task = self.client.request("POST", "/tasks", {"instruction": "buffer", "request_id": "cancel"})
        result = self.client.request("POST", self.client.task_path(task["id"]) + "/cancel", {})
        self.assertEqual(result["state"], "cancelled")
        with self.assertRaises(RuntimeError):
            self.client.request("POST", "/execute", {"code": "print(1)"})
        self.bridge.stop()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.client.status()["connected"])

    def exercise_mcp(self, server_file):
        async def exercise():
            from mcp import Client, StdioServerParameters
            env = dict(os.environ, QUERYGIS_CONNECTION_FILE=str(self.path), QUERYGIS_MCP_PYTHON=sys.executable)
            async with Client(StdioServerParameters(command=sys.executable, args=[str(server_file)], env=env)) as session:
                listed = await session.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                self.assertEqual(set(tools), {"get_connection_status", "submit_task", "get_task_status", "get_task_result", "cancel_task"})
                self.assertEqual(set(tools["submit_task"].input_schema["properties"]), {"instruction", "request_id", "mode"})
                self.assertTrue(tools["get_connection_status"].annotations.read_only_hint)
                status = await session.call_tool("get_connection_status", {})
                self.assertFalse(status.is_error)
                task = await session.call_tool("submit_task", {"instruction": "학교 주변 버퍼", "request_id": "stdio"})
                self.assertFalse(task.is_error)
                task_id = self.store.next_queued()
                self.assertIsNotNone(task_id)
                result = await session.call_tool("cancel_task", {"task_id": task_id})
                self.assertFalse(result.is_error)
        asyncio.run(exercise())

    def test_real_mcp_stdio(self):
        self.exercise_mcp(SERVER / "server.py")

    def test_plugin_zip_runs_from_an_independent_cache_directory(self):
        spec = importlib.util.spec_from_file_location("querygis_build", ROOT / "scripts" / "build_plugin.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        companion, codex = build.build()
        cache = Path(self.temporary.name) / "plugin-cache"
        with ZipFile(codex) as package:
            names = set(package.namelist())
            self.assertIn("querygis/plugin.json", names)
            self.assertIn("querygis/mcp.json", names)
            package.extractall(cache)
        with ZipFile(companion) as package:
            self.assertNotIn("querygis_codex_connector/query_gis.py", package.namelist())
            self.assertNotIn("querygis_codex_connector/provider.py", package.namelist())
        self.exercise_mcp(cache / "querygis" / "server" / "launch.py")

    def test_codex_compatible_initialize_protocol(self):
        import queue
        import threading
        lines = queue.Queue()
        env = dict(os.environ, QUERYGIS_CONNECTION_FILE=str(self.path))
        process = subprocess.Popen([sys.executable, "-u", str(SERVER / "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        def read_lines():
            for line in process.stdout:
                lines.put(json.loads(line))
        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()
        def send(value):
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
        def receive(request_id):
            while True:
                item = lines.get(timeout=10)
                if item.get("id") == request_id:
                    return item
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "codex-test", "version": "1"}}})
            self.assertNotIn("error", receive(1))
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertEqual(len(receive(2)["result"]["tools"]), 5)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=1)
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
