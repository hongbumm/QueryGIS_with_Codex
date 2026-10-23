"""Exercise the real local bridge and provider contract without paid API requests."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "qgis_plugin"))
from querygis_with_codex.tasks import TaskStore, TERMINAL
from querygis_with_codex.bridge import BridgeServer
from querygis_with_codex.provider import ProviderConfig, generate_plan, parse_plan
from codex_mcp.client import QueryGISClient


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore()
        self.payload = {"instruction": "선택한 레이어에 500m 버퍼", "request_id": "request-1"}

    def test_delivery_retries_do_not_duplicate_execution(self):
        first = self.store.submit(self.payload)
        self.assertEqual(first["id"], self.store.submit(self.payload)["id"])
        self.store.update(first["id"], "planning", "planning")
        self.store.update(first["id"], "running", "running")
        self.store.update(first["id"], "succeeded", "done", {"layers": ["buffer"]})
        self.assertEqual(self.store.submit(self.payload)["state"], "succeeded")
        with self.assertRaises(ValueError):
            self.store.submit({**self.payload, "instruction": "different task"})

    def test_code_and_credentials_cannot_be_submitted_as_task_fields(self):
        for field in ("code", "python", "api_key", "command", "sql"):
            with self.assertRaises(ValueError):
                self.store.submit({**self.payload, field: "forbidden"})

    def test_cancelled_planning_cannot_later_execute(self):
        task = self.store.submit(self.payload)
        self.store.update(task["id"], "planning", "planning")
        self.store.cancel(task["id"])
        self.assertFalse(self.store.update(task["id"], "running", "late response"))
        self.assertEqual(self.store.public(task["id"])["state"], "cancelled")

    def test_running_cancel_is_cooperative(self):
        task = self.store.submit(self.payload)
        self.store.update(task["id"], "planning", "planning")
        self.store.update(task["id"], "running", "running")
        result = self.store.cancel(task["id"])
        self.assertEqual(result["state"], "running")
        self.assertTrue(self.store.details(task["id"])["cancel_event"].is_set())

    def test_missing_request_id_and_wrong_layer_types_rejected(self):
        for payload in ({"instruction": "buffer"}, {**self.payload, "layer_ids": "bad"},
                        {**self.payload, "mode": "execute-python"}, [],
                        {**self.payload, "instruction": " "}):
            with self.assertRaises(ValueError):
                self.store.submit(payload)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "connection.json"
        self.store = TaskStore()
        self.bridge = BridgeServer(self.store, self.path)
        self.bridge.set_snapshot({"provider_configured": True, "layers": [{"id": "schools", "name": "학교"}]})
        self.bridge.start()
        self.client = QueryGISClient(self.path)

    def tearDown(self):
        self.bridge.stop()
        self.temporary.cleanup()

    def test_task_round_trip_and_result_contract(self):
        self.assertTrue(self.client.status()["connected"])
        task = self.client.request("POST", "/tasks", {"instruction": "500m 버퍼", "request_id": "roundtrip"})
        self.assertEqual(self.store.next_queued(), task["id"])
        self.store.update(task["id"], "planning", "QueryGIS planning")
        self.store.update(task["id"], "awaiting_approval", "review in QGIS")
        self.assertEqual(self.client.request("GET", self.client.task_path(task["id"]))["state"], "awaiting_approval")
        self.store.update(task["id"], "running", "QGIS executing")
        self.store.update(task["id"], "succeeded", "done", {"layers": [{"id": "buffer_1"}], "stdout": "1 feature"})
        result = self.client.request("GET", self.client.task_path(task["id"]))
        self.assertEqual(result["result"]["layers"][0]["id"], "buffer_1")
        self.assertNotIn("payload", result)
        self.assertNotIn("token", result)
        self.assertNotIn("api_key", result)

    def test_bridge_rejects_browser_origin_and_missing_token(self):
        data = json.loads(self.path.read_text())
        url = "http://127.0.0.1:%d/health" % data["port"]
        for headers in ({}, {"Authorization": "Bearer " + data["token"], "Origin": "https://example.com"}):
            with self.assertRaises(HTTPError) as caught:
                build_opener(ProxyHandler({})).open(Request(url, headers=headers), timeout=3)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()

    def test_second_qgis_session_does_not_replace_live_connection(self):
        with self.assertRaises(RuntimeError):
            BridgeServer(TaskStore(), self.path).start()
        self.assertTrue(self.client.status()["connected"])

    def test_api_key_missing_does_not_accept_tasks(self):
        self.bridge.set_snapshot({"provider_configured": False})
        with self.assertRaisesRegex(RuntimeError, "API Key"):
            self.client.request("POST", "/tasks", {"instruction": "buffer", "request_id": "not-ready"})

    def test_cancel_and_shutdown(self):
        task = self.client.request("POST", "/tasks", {"instruction": "buffer", "request_id": "cancel"})
        result = self.client.request("POST", self.client.task_path(task["id"]) + "/cancel", {})
        self.assertEqual(result["state"], "cancelled")
        self.bridge.stop()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.client.status()["connected"])

    def test_raw_execution_route_is_not_available(self):
        with self.assertRaises(RuntimeError):
            self.client.request("POST", "/execute", {"code": "print(1)"})
        with self.assertRaisesRegex(ValueError, "Invalid"):
            self.client.task_path("../../execute")

    def test_real_mcp_stdio_connection(self):
        async def exercise():
            from mcp import Client, StdioServerParameters
            env = dict(os.environ, QUERYGIS_CONNECTION_FILE=str(self.path))
            params = StdioServerParameters(command=sys.executable,
                args=[str(ROOT / "codex_mcp" / "server.py")], env=env)
            async with Client(params) as session:
                listed = await session.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                self.assertEqual(set(tools), {"get_connection_status", "submit_task", "get_task_status", "get_task_result", "cancel_task"})
                schema = tools["submit_task"].input_schema
                self.assertNotIn("code", schema["properties"])
                self.assertNotIn("api_key", schema["properties"])
                self.assertTrue(tools["get_connection_status"].annotations.read_only_hint)
                self.assertFalse(tools["submit_task"].annotations.read_only_hint)
                status = await session.call_tool("get_connection_status", {})
                self.assertFalse(status.is_error)
                task = await session.call_tool("submit_task", {"instruction": "학교 주변 버퍼", "request_id": "stdio"})
                self.assertFalse(task.is_error)
                task_id = self.store.next_queued()
                self.assertIsNotNone(task_id)
                cancelled = await session.call_tool("cancel_task", {"task_id": task_id})
                self.assertFalse(cancelled.is_error)
                self.assertEqual(self.store.public(task_id)["state"], "cancelled")
        asyncio.run(exercise())

    def test_codex_compatible_initialize_protocol(self):
        import queue
        import threading
        lines = queue.Queue()
        env = dict(os.environ, QUERYGIS_CONNECTION_FILE=str(self.path))
        process = subprocess.Popen([sys.executable, "-u", str(ROOT / "codex_mcp" / "server.py")],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env)
        def read_lines():
            for line in process.stdout:
                lines.put(json.loads(line))
        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()
        def send(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        def receive(request_id):
            while True:
                message = lines.get(timeout=10)
                if message.get("id") == request_id:
                    return message
        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "codex-compatibility-test", "version": "1"}}})
            reply = receive(1)
            self.assertNotIn("error", reply)
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools = receive(2)["result"]["tools"]
            self.assertIn("submit_task", {tool["name"] for tool in tools})
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


class ProviderTests(unittest.TestCase):
    def test_openai_request_and_response(self):
        config = ProviderConfig("openai", "test-model", "test-key-do-not-use")
        response = {"output": [{"type": "message", "content": [{"type": "output_text",
            "text": json.dumps({"message": "버퍼 생성", "code": "print('done')"})}]}]}
        with patch("querygis_with_codex.provider._post", return_value=response) as post:
            result = generate_plan(config, "buffer", {"layers": []})
        self.assertIn("print", result["code"])
        self.assertFalse(post.call_args.args[1]["store"])
        self.assertNotIn("test-key-do-not-use", json.dumps(post.call_args.args[1]))

    def test_ask_mode_never_executes_generated_code(self):
        response = {"candidates": [{"content": {"parts": [{"text": '{"message":"explain","code":"print(1)"}'}]}}]}
        with patch("querygis_with_codex.provider._post", return_value=response):
            plan = generate_plan(ProviderConfig("gemini", "test", "key"), "explain", {}, mode="ask")
        self.assertEqual(plan["code"], "")

    def test_legacy_backend_and_code_fences(self):
        response = {"response": "버퍼 생성\n```python\nprint('buffer')\n```"}
        with patch("querygis_with_codex.provider._post", return_value=response):
            plan = generate_plan(ProviderConfig("backend", "test", "key"), "buffer", {})
        self.assertEqual(plan["code"], "print('buffer')")

    def test_clear_provider_errors_and_bad_response(self):
        for raw in ("", '{"message": "missing code"}', '[]'):
            with self.assertRaises(ValueError):
                parse_plan(raw)
        with self.assertRaisesRegex(ValueError, "API Key"):
            generate_plan(ProviderConfig("openai", "model", ""), "buffer", {})
        with self.assertRaises(ValueError):
            generate_plan(ProviderConfig("backend", "model", "key", "http://example.com"), "buffer", {})


if __name__ == "__main__":
    unittest.main()
