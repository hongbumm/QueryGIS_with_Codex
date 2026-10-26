"""Install only our companion into an existing Windows QGIS profile."""
import configparser
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "querygis_codex_connector"


def update_activation(text, disable_prototype=False):
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "[PythonPlugins]"), None)
    if start is None:
        lines += ["", "[PythonPlugins]"]
        start = len(lines) - 1
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    changes = {NAME: "true"}
    if disable_prototype:
        changes["querygis_with_codex"] = "false"
    for name, value in changes.items():
        found = next((i for i in range(start + 1, end)
                      if lines[i].split("=", 1)[0].strip().lower() == name), None)
        if found is not None:
            lines[found] = name + "=" + value
        else:
            lines.insert(end, name + "=" + value)
            end += 1
    return newline.join(lines) + newline


def install():
    if os.name != "nt":
        print("Windows 외 환경에서는 빌드된 ZIP을 QGIS에서 설치하세요.")
        return
    profile = Path(os.environ["APPDATA"]) / "QGIS/QGIS3/profiles/default"
    plugins = profile / "python/plugins"
    if not plugins.is_dir():
        print("QGIS 기본 프로필이 없습니다. dist의 연결부 ZIP을 QGIS에서 설치하세요.")
        return
    destination = plugins / NAME
    if destination.exists():
        metadata = configparser.ConfigParser()
        metadata.read(destination / "metadata.txt", encoding="utf-8-sig")
        if metadata.get("general", "name", fallback="") != "QueryGIS Codex Connector":
            raise RuntimeError("같은 폴더에 다른 플러그인이 있습니다. 덮어쓰지 않습니다")
    shutil.copytree(ROOT / "qgis_plugin" / NAME, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Do not race a running QGIS instance that may rewrite its settings on exit.
    processes = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", check=True)
    if re.search(r'"qgis[^"\r\n]*\.exe"', processes.stdout, re.IGNORECASE):
        print("연결부 파일을 설치했습니다. QGIS 재시작 후 플러그인 관리에서 활성화하세요.")
        return
    legacy = configparser.ConfigParser()
    legacy.read(plugins / "querygis_with_codex" / "metadata.txt", encoding="utf-8-sig")
    disable = (legacy.get("general", "name", fallback="") == "QueryGIS with Codex" and
               legacy.get("general", "version", fallback="") == "0.1.0")
    settings = profile / "QGIS/QGIS3.ini"
    settings.parent.mkdir(parents=True, exist_ok=True)
    raw = settings.read_bytes() if settings.exists() else b""
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    updated = update_activation(raw.decode(encoding), disable)
    temporary = settings.with_suffix(".querygis-codex.tmp")
    temporary.write_bytes(updated.encode(encoding))
    os.replace(temporary, settings)
    print("QGIS 연결부 설치·활성화 완료. 기존 QueryGIS 플러그인과 서버 설정은 유지했습니다.")
    if disable:
        print("이전 QueryGIS with Codex 0.1 실험본은 비활성화했습니다. 파일은 보존합니다.")


if __name__ == "__main__":
    install()
