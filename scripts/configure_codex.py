"""Register this checkout's local MCP adapter with Codex, never a provider API key."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "querygis_with_codex"


def find_codex():
    command = shutil.which("codex")
    if command:
        return command
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    candidates = list(local.glob("*/codex.exe"))
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    raise RuntimeError("Codex 실행 파일을 찾지 못했습니다. Codex를 설치하거나 PATH에 추가하세요")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        raise RuntimeError("먼저 scripts/setup.ps1을 실행해 MCP 환경을 준비하세요")
    server = ROOT / "codex_mcp" / "server.py"
    if args.print_config:
        print(json.dumps({"name": NAME, "command": str(python), "args": [str(server)]}, indent=2))
        return
    codex = find_codex()
    old = subprocess.run([codex, "mcp", "get", NAME, "--json"], capture_output=True, text=True)
    if old.returncode == 0:
        existing = json.loads(old.stdout).get("transport", {})
        if existing.get("command") == str(python) and existing.get("args") == [str(server)]:
            print("Codex MCP connection is already configured for this checkout.")
            return
        raise RuntimeError("같은 이름의 Codex 연결이 이미 있습니다. 기존 설정을 확인한 뒤 다시 등록하세요")
    subprocess.run([codex, "mcp", "add", NAME, "--", str(python), str(server)], check=True)
    print("Codex 연결 등록 완료. 새 채팅에서 QueryGIS 도구를 사용하세요.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
