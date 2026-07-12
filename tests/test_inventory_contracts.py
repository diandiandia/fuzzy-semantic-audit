import os
import shutil
import tempfile
import unittest

from src_v3.core.models import LanguageShard, RepoProfile
from src_v3.core.provider_registry import resolve_provider_set
from src_v3.inventory.language_sharder import shard_repository
from src_v3.inventory.repo_profiler import scan_repository


class TestInventoryContracts(unittest.TestCase):
    def setUp(self):
        self.repo_dir = tempfile.mkdtemp()
        self.workspace_dir = os.path.join(self.repo_dir, ".audit_workspace_v3")
        os.makedirs(self.workspace_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.repo_dir)

    def write_file(self, rel_path, content):
        abs_path = os.path.join(self.repo_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_profiler_and_sharder_exclude_workspace_history_and_artifacts(self):
        self.write_file("src/app.py", "def run():\n    return 1\n")
        self.write_file("src/policy.custom", "policy text\n")
        self.write_file(".audit_workspace_v3/cache/leak.py", "def leak(): pass\n")
        self.write_file("old_audit/audit_plan.json", "{}\n")
        self.write_file("old_audit/evidence/leak.go", "package main\n")
        self.write_file("node_modules/pkg/index.js", "module.exports = 1\n")
        self.write_file("build/generated.java", "class Generated {}\n")

        profile = scan_repository(self.repo_dir, self.workspace_dir)
        shards = shard_repository(self.repo_dir, profile, self.workspace_dir)
        shard_paths = sorted(path for shard in shards for path in shard.paths)
        shard_langs = sorted({shard.lang for shard in shards})

        self.assertEqual(profile.languages, ["python"])
        self.assertEqual(profile.directory_roles["old_audit"], "workspace_artifact")
        self.assertEqual(profile.directory_roles["node_modules"], "workspace_artifact")
        self.assertEqual(profile.directory_roles["build"], "workspace_artifact")
        self.assertEqual(shard_paths, ["src/app.py", "src/policy.custom"])
        self.assertEqual(shard_langs, ["python", "unsupported"])

    def test_provider_set_contains_combination_trace_and_degradations(self):
        profile = RepoProfile(frameworks=["django", "fastapi"])
        shard = LanguageShard(shard_id="python-root", lang="python", paths=["app.py"])
        degradations = []

        provider_set = resolve_provider_set(
            profile,
            shard,
            {
                "semantic_preference": ["lsp", "ctags", "null"],
                "embedding_preference": "openai"
            },
            repo_path=self.repo_dir,
            ir_store=None,
            degradation_list=degradations
        )

        self.assertEqual(provider_set["parser"], "TreeSitterNativeProvider")
        self.assertEqual(provider_set["semantic"], "NullProvider")
        self.assertEqual(provider_set["embedding"], "KeywordFallbackProvider")
        self.assertEqual(provider_set["frameworks"], ["DjangoPack", "GenericFrameworkProvider"])
        self.assertTrue(any("lsp_server_address is missing" in reason for reason in degradations))
        self.assertTrue(any(step["kind"] == "semantic" for step in provider_set["selector_trace"]))


if __name__ == "__main__":
    unittest.main()
