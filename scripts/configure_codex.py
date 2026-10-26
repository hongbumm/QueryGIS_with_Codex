"""Prepare the local runtime and install QueryGIS as a real Codex plugin."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTOR = "querygis@querygis-local"


def find_codex():
    command = shutil.which("codex")
    if command:
        return command
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    candidates = list(local.glob("*/codex.exe"))
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    raise RuntimeError("Codex를 설치하거나 실행 파일을 PATH에 추가하세요")


def runtime_file():
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "QueryGIS_with_Codex" / "runtime.json"


def install():
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        raise RuntimeError("먼저 scripts/setup.ps1로 MCP 환경을 준비하세요")
    subprocess.run([str(python), "-c", "import mcp"], check=True)
    runtime = runtime_file()
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(json.dumps({"version": 1, "python": str(python)}), encoding="utf-8")
    codex = find_codex()
    subprocess.run([codex, "plugin", "marketplace", "add", str(ROOT), "--json"], check=True)
    subprocess.run([codex, "plugin", "add", SELECTOR, "--json"], check=True)
    # Retire only the exact standalone prototype connection created by version 0.1.
    old = subprocess.run([codex, "mcp", "get", "querygis_with_codex", "--json"], capture_output=True, text=True)
    if old.returncode == 0:
        transport = json.loads(old.stdout).get("transport", {})
        if (transport.get("command") == str(python) and
                transport.get("args") == [str(ROOT / "codex_mcp" / "server.py")]):
            subprocess.run([codex, "mcp", "remove", "querygis_with_codex"], check=True)
    print("QueryGIS Codex 플러그인 설치 완료. 새 채팅에서 사용하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    try:
        if args.print_config:
            print(json.dumps({"plugin": SELECTOR, "marketplace": str(ROOT),
                              "runtime_file": str(runtime_file())}, indent=2))
        else:
            install()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
