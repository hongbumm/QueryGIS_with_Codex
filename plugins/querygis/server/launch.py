"""Resolve the locally prepared SDK runtime, including when the plugin is cached."""
import importlib.util
import json
import os
import sys
from pathlib import Path


def runtime_file():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "QueryGIS_with_Codex" / "runtime.json"


def main():
    python = os.environ.get("QUERYGIS_MCP_PYTHON")
    if not python:
        try:
            data = json.loads(runtime_file().read_text(encoding="utf-8"))
            if data.get("version") == 1:
                python = data.get("python")
        except (OSError, ValueError):
            pass
    if not python and importlib.util.find_spec("mcp"):
        python = sys.executable
    if not python or not Path(python).is_file():
        raise RuntimeError("QueryGIS 플러그인 실행 환경이 없습니다. 저장소의 scripts/setup.ps1을 먼저 실행하세요")
    os.execv(str(python), [str(python), "-u", str(Path(__file__).with_name("server.py"))])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
