import os
import tempfile
import unittest
import json
from src_v4.inventory.language_sharder import LanguageDiscoverer

class TestLanguageDiscoverer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def test_discover_languages(self):
        # Create dummy directory structure
        os.makedirs(os.path.join(self.repo_path, "service/src"))
        os.makedirs(os.path.join(self.repo_path, "hal"))
        os.makedirs(os.path.join(self.repo_path, "node_modules/some_dep"))  # Should be excluded
        os.makedirs(os.path.join(self.repo_path, ".git"))  # Should be excluded
        
        # Create dummy source files
        java_file = os.path.join(self.repo_path, "service/src/BluetoothManager.java")
        cpp_file = os.path.join(self.repo_path, "hal/bluetooth_interface.cpp")
        py_file = os.path.join(self.repo_path, "scripts/helper.py")
        excluded_file = os.path.join(self.repo_path, "node_modules/some_dep/index.js")
        
        os.makedirs(os.path.join(self.repo_path, "scripts"), exist_ok=True)
        
        for fpath in [java_file, cpp_file, py_file, excluded_file]:
            with open(fpath, "w") as f:
                f.write("// dummy code")
                
        discoverer = LanguageDiscoverer()
        profile = discoverer.discover(self.repo_path)
        
        # Check profile contents
        self.assertEqual(profile["repo_path"], os.path.abspath(self.repo_path))
        self.assertIn("java", profile["languages"])
        self.assertIn("cpp", profile["languages"])
        self.assertIn("python", profile["languages"])
        self.assertNotIn("javascript", profile["languages"]) # node_modules excluded
        
        # Check relative paths
        self.assertEqual(profile["languages"]["java"], ["service/src/BluetoothManager.java"])
        self.assertEqual(profile["languages"]["cpp"], ["hal/bluetooth_interface.cpp"])
        
        # Check file existence of repo_profile.json
        profile_json_path = os.path.join(self.repo_path, "repo_profile.json")
        self.assertTrue(os.path.exists(profile_json_path))
        with open(profile_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["repo_path"], os.path.abspath(self.repo_path))

if __name__ == "__main__":
    unittest.main()
