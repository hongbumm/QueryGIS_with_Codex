"""Package the Codex plugin and the small QGIS companion separately."""
import ast
import configparser
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def archive(source, destination, prefix):
    with ZipFile(destination, "w", ZIP_DEFLATED) as output:
        for path in sorted(source.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                if path.suffix == ".py":
                    ast.parse(path.read_text(encoding="utf-8-sig"))
                output.write(path, prefix + path.relative_to(source).as_posix())
    return destination


def build():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    qgis = ROOT / "qgis_plugin" / "querygis_codex_connector"
    metadata = configparser.ConfigParser()
    metadata.read(qgis / "metadata.txt", encoding="utf-8")
    version = metadata["general"]["version"]
    companion = archive(qgis, dist / ("querygis_codex_connector-" + version + ".zip"), "querygis_codex_connector/")
    plugin = ROOT / "plugins" / "querygis"
    manifest = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    codex = archive(plugin, dist / ("querygis-codex-plugin-" + manifest["version"] + ".zip"), "querygis/")
    print(companion)
    print(codex)
    return companion, codex


if __name__ == "__main__":
    build()
