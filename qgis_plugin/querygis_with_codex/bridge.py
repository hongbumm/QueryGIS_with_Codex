"""Authenticated loopback mailbox. HTTP threads never touch a QGIS object."""
import hmac
import json
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import ProxyHandler, Request, build_opener

from .tasks import connection_path


class BridgeServer:
    def __init__(self, store, discovery_file=None):
        self.store = store
        self.discovery_file = discovery_file or connection_path()
        self.token = secrets.token_urlsafe(32)
        self._lock = threading.Lock()
        self._snapshot = {"provider_configured": False, "layers": [], "project_crs": ""}
        self._server = None
        self._thread = None

    def set_snapshot(self, snapshot):
        with self._lock:
            self._snapshot = json.loads(json.dumps(snapshot))

    def snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self._snapshot))

    @property
    def running(self):
        return self._server is not None

    def _check_existing(self):
        if not self.discovery_file.exists():
            return
        try:
            old = json.loads(self.discovery_file.read_text(encoding="utf-8"))
            port = old["port"]
            if type(port) is not int or not 1 <= port <= 65535:
                return
            req = Request("http://127.0.0.1:%d/health" % port,
                          headers={"Authorization": "Bearer " + old["token"]})
            with build_opener(ProxyHandler({})).open(req, timeout=1) as response:
                active = json.load(response).get("service") == "querygis-with-codex"
        except Exception:
            return
        if active:
            raise RuntimeError("다른 QGIS 세션이 이미 Codex에 연결되어 있습니다")

    def start(self):
        if self.running:
            return
        self._check_existing()
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "QueryGIS/0.1"

            def log_message(self, *args):
                pass

            def _reply(self, status, data):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self):
                expected_hosts = {"127.0.0.1:%d" % self.server.server_port,
                                  "localhost:%d" % self.server.server_port}
                auth = self.headers.get("Authorization", "")
                if (self.headers.get("Origin") is not None or
                        self.headers.get("Host") not in expected_hosts or
                        not hmac.compare_digest(auth, "Bearer " + bridge.token)):
                    self._reply(403, {"error": "Unauthorized local connection"})
                    return False
                return True

            def do_GET(self):
                if not self._authorized():
                    return
                if self.path == "/health":
                    self._reply(200, {"service": "querygis-with-codex", "version": "0.1.0",
                                      **bridge.snapshot()})
                    return
                match = re.fullmatch(r"/tasks/([a-f0-9]{32})", self.path)
                if match:
                    try:
                        self._reply(200, bridge.store.public(match.group(1)))
                    except KeyError:
                        self._reply(404, {"error": "Unknown task ID"})
                else:
                    self._reply(404, {"error": "Unknown route"})

            def do_POST(self):
                if not self._authorized():
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._reply(400, {"error": "Invalid content length"})
                    return
                if not 0 < length <= 65536 or self.headers.get_content_type() != "application/json":
                    self._reply(400, {"error": "A JSON body up to 64 KB is required"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length))
                    if self.path == "/tasks":
                        if not bridge.snapshot().get("provider_configured"):
                            self._reply(409, {"error": "QueryGIS 패널에서 공급자, 모델, API Key를 입력하세요"})
                            return
                        self._reply(202, bridge.store.submit(payload))
                        return
                    match = re.fullmatch(r"/tasks/([a-f0-9]{32})/cancel", self.path)
                    if match:
                        if payload != {}:
                            raise ValueError("Cancel request body must be empty")
                        self._reply(200, bridge.store.cancel(match.group(1)))
                        return
                    self._reply(404, {"error": "Unknown route"})
                except KeyError:
                    self._reply(404, {"error": "Unknown task ID"})
                except (ValueError, UnicodeError) as exc:
                    self._reply(400, {"error": str(exc)})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True,
                                        name="QueryGIS-Codex-mailbox")
        self._thread.start()
        try:
            self.discovery_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"version": 1, "port": self._server.server_port, "token": self.token, "pid": os.getpid()}
            temporary = self.discovery_file.with_suffix(".tmp")
            fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(str(temporary), str(self.discovery_file))
            os.chmod(str(self.discovery_file), 0o600)
        except Exception:
            self.stop()
            raise

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        try:
            data = json.loads(self.discovery_file.read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                self.discovery_file.unlink()
        except (OSError, ValueError):
            pass
