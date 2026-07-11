import os
import shutil
import tempfile
import unittest

from src_v3.core.models import FileNode, LanguageShard
from src_v3.inventory.capability_resolver import resolve_effective_capability
from src_v3.storage.ir_store import IRStore


class Provider:
    provider_name = "TestSemanticProvider"

    def __init__(self, use_fallback):
        self.use_fallback = use_fallback


class TestCapabilityResolver(unittest.TestCase):
    def setUp(self):
        self.workspace_dir = tempfile.mkdtemp()
        self.store = IRStore(self.workspace_dir)
        self.store.save([
            FileNode("file_app.py", "file", "python", "app.py", "", {"start": 1, "end": 1}, {"parse_mode": "tree_sitter"})
        ], [])
        self.shard = LanguageShard("python-root", "python", ["app.py"], provider_set={"semantic": "CtagsProvider"})
        self.semantic_index = {"sym": {"definitions": [{"file": "app.py"}], "references": [{"file": "app.py"}]}}

    def tearDown(self):
        shutil.rmtree(self.workspace_dir)

    def test_fallback_results_do_not_upgrade_to_l2(self):
        self.assertEqual(resolve_effective_capability(self.shard, self.store, self.semantic_index, Provider(True)), "L1")

    def test_real_semantic_results_upgrade_to_l2(self):
        self.assertEqual(resolve_effective_capability(self.shard, self.store, self.semantic_index, Provider(False)), "L2")


if __name__ == "__main__":
    unittest.main()
