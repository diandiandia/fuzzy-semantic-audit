import os
import shutil
import tempfile
import unittest

from src_v3.core.models import RepoProfile
from src_v3.inventory.framework_detector import detect_frameworks


class TestFrameworkBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.tmp_dir, "project")
        self.workspace_dir = os.path.join(self.project_dir, ".audit_workspace_v3")
        os.makedirs(self.workspace_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_android_manifest_inside_workspace_is_ignored(self):
        os.makedirs(os.path.join(self.workspace_dir, "reports"), exist_ok=True)
        with open(os.path.join(self.workspace_dir, "reports", "AndroidManifest.xml"), "w", encoding="utf-8") as f:
            f.write("<manifest />")

        detected = detect_frameworks(self.project_dir, RepoProfile(), self.workspace_dir)
        self.assertNotIn("android", detected)


if __name__ == "__main__":
    unittest.main()
