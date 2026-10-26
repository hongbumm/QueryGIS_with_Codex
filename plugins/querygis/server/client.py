import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class QueryGISClient:
    def __init__(self, discovery_file=None):
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
        self.discovery_file = Path(discovery_file or os.environ.get(
            "QUERYGIS_CONNECTION_FILE", str(base / "QueryGIS_with_Codex" / "connection.json")))

    def request(self, method, path, payload=None):
        try:
            connection = json.loads(self.discovery_file.read_text(encoding="utf-8"))
            port, token = connection["port"], connection["token"]
            if (connection.get("version") != 2 or type(port) is not int or not 1 <= port <= 65535
                    or not isinstance(token, str) or not 32 <= len(token) <= 128):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise RuntimeError("QGIS에서 기존 QueryGIS와 QueryGIS Codex Connector를 활성화한 뒤 'QueryGIS ↔ Codex 연결'을 누르세요") from None
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request("http://127.0.0.1:%d%s" % (port, path), data=body,
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method=method)
        try:
            # Local traffic must never be routed through a system HTTP proxy.
            with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                message = json.load(exc).get("error", "QueryGIS 요청 실패")
            except (ValueError, AttributeError):
                message = "QueryGIS 요청 실패 (HTTP %d)" % exc.code
            finally:
                exc.close()
            raise RuntimeError(message) from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("QueryGIS 연결이 종료되었습니다. QGIS 패널에서 다시 연결하세요") from None

    def status(self):
        try:
            return {"connected": True, **self.request("GET", "/health")}
        except RuntimeError as exc:
            return {"connected": False, "message": str(exc)}

    @staticmethod
    def task_path(task_id):
        import re
        if not isinstance(task_id, str) or not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise ValueError("Invalid QueryGIS task ID")
        return "/tasks/" + task_id
