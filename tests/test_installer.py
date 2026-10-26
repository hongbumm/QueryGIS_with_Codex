import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("qgis_installer", Path(__file__).resolve().parents[1] / "scripts/install_qgis_connector.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_activation_preserves_original_plugins_and_service_settings(self):
        original = "[PythonPlugins]\r\nQueryGIS-main=true\r\nQueryGIS_Local=true\r\nquerygis_with_codex=true\r\n[QueryGIS]\r\napi_key=existing-encoded-service-key\r\nserver=https://existing-server.example\r\n"
        updated = installer.update_activation(original, disable_prototype=True)
        self.assertIn("QueryGIS-main=true\r\n", updated)
        self.assertIn("QueryGIS_Local=true\r\n", updated)
        self.assertIn("api_key=existing-encoded-service-key\r\n", updated)
        self.assertIn("server=https://existing-server.example\r\n", updated)
        self.assertIn("querygis_with_codex=false\r\n", updated)
        self.assertIn("querygis_codex_connector=true\r\n", updated)
        self.assertEqual(installer.update_activation(updated, True), updated)

    def test_new_section_and_unrelated_prototype_are_preserved(self):
        original = "[Other]\nvalue=keep\n"
        updated = installer.update_activation(original)
        self.assertIn(original, updated)
        self.assertNotIn("querygis_with_codex", updated)
        self.assertIn("[PythonPlugins]\nquerygis_codex_connector=true\n", updated)
