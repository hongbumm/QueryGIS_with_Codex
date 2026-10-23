"""Build a QGIS-installable ZIP without credentials, dev dependencies or caches."""
import ast
import configparser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "qgis_plugin" / "querygis_with_codex"


def build():
    metadata = configparser.ConfigParser()
    metadata.read(SOURCE / "metadata.txt", encoding="utf-8")
    version = metadata["general"]["version"]
    destination = ROOT / "dist" / ("querygis_with_codex-" + version + ".zip")
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for source in sorted(SOURCE.rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts and source.suffix in {".py", ".txt", ".png", ".qrc"}:
                if source.suffix == ".py":
                    ast.parse(source.read_text(encoding="utf-8-sig"))
                archive.write(source, "querygis_with_codex/" + source.relative_to(SOURCE).as_posix())
    print(destination)
    return destination


if __name__ == "__main__":
    build()
