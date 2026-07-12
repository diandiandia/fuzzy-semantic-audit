import unittest
import tempfile
import shutil
import os
import sys
import subprocess
import json
from pathlib import Path
from src_v3.m2_index.index_cache import IndexCache

class TestIndexReuse(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp_dir) / "cache"
        self.cache = IndexCache(self.cache_dir)
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_cache_miss_initially(self):
        fingerprint = {
            "parser_version": "1.0.0",
            "schema_version": "3",
            "embedding_model": "KeywordFallbackProvider",
            "embedding_config_hash": "embed_hash",
            "semantic_provider": "CtagsProvider",
            "semantic_config_hash": "semantic_hash",
            "chunking_config_hash": "chunk_hash",
            "content_hash": "content_1"
        }
        self.assertFalse(self.cache.is_valid("app.py", fingerprint))

    def test_cache_hit_after_put(self):
        fingerprint = {
            "parser_version": "1.0.0",
            "schema_version": "3",
            "embedding_model": "KeywordFallbackProvider",
            "embedding_config_hash": "embed_hash",
            "semantic_provider": "CtagsProvider",
            "semantic_config_hash": "semantic_hash",
            "chunking_config_hash": "chunk_hash",
            "content_hash": "content_1"
        }
        
        # Save record
        record = {
            "path": "app.py",
            "content_hash": "content_1",
            "language": "python",
            "parser_version": "1.0.0",
            "schema_version": "3",
            "embedding_config_hash": "embed_hash",
            "symbols": {"sym1": "data"},
            "chunks": [],
            "edges": [],
            "embedding_refs": []
        }
        
        self.cache.put_file_record("app.py", record)
        self.cache.manifest["files"]["app.py"] = fingerprint
        self.cache.save_manifest()
        
        # Reload cache to verify persistence
        new_cache = IndexCache(self.cache_dir)
        self.assertTrue(new_cache.is_valid("app.py", fingerprint))
        
        retrieved = new_cache.get_file_record("app.py")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["symbols"]["sym1"], "data")

    def test_cache_invalidation_on_change(self):
        fingerprint_orig = {
            "parser_version": "1.0.0",
            "schema_version": "3",
            "embedding_model": "KeywordFallbackProvider",
            "embedding_config_hash": "embed_hash",
            "semantic_provider": "CtagsProvider",
            "semantic_config_hash": "semantic_hash",
            "chunking_config_hash": "chunk_hash",
            "content_hash": "content_1"
        }
        
        # Put record
        record = {
            "path": "app.py",
            "content_hash": "content_1",
            "language": "python",
            "parser_version": "1.0.0",
            "schema_version": "3",
            "embedding_config_hash": "embed_hash",
            "symbols": {},
            "chunks": [],
            "edges": [],
            "embedding_refs": []
        }
        self.cache.put_file_record("app.py", record)
        self.cache.manifest["files"]["app.py"] = fingerprint_orig
        self.cache.save_manifest()
        
        # 1. Content hash change -> invalid
        fp_changed_hash = fingerprint_orig.copy()
        fp_changed_hash["content_hash"] = "content_2"
        self.assertFalse(self.cache.is_valid("app.py", fp_changed_hash))
        
        # 2. Parser version change -> invalid
        fp_changed_parser = fingerprint_orig.copy()
        fp_changed_parser["parser_version"] = "2.0.0"
        self.assertFalse(self.cache.is_valid("app.py", fp_changed_parser))
        
        # 3. Schema version change -> invalid
        fp_changed_schema = fingerprint_orig.copy()
        fp_changed_schema["schema_version"] = "4"
        self.assertFalse(self.cache.is_valid("app.py", fp_changed_schema))
        
        # 4. Semantic provider/config change -> invalid
        fp_changed_semantic = fingerprint_orig.copy()
        fp_changed_semantic["semantic_config_hash"] = "semantic_hash_2"
        self.assertFalse(self.cache.is_valid("app.py", fp_changed_semantic))
        
        # 5. Delete record -> invalid
        self.cache.delete_file_record("app.py")
        self.assertFalse(self.cache.is_valid("app.py", fingerprint_orig))
        self.assertIsNone(self.cache.get_file_record("app.py"))

    def test_build_index_cli_integration(self):
        # Create a mock project directory
        project_dir = os.path.join(self.tmp_dir, "mock_project")
        os.makedirs(project_dir, exist_ok=True)
        
        # Create two source files
        with open(os.path.join(project_dir, "file1.py"), "w") as f:
            f.write("def func1():\n    pass\n")
        with open(os.path.join(project_dir, "file2.py"), "w") as f:
            f.write("def func2():\n    pass\n")
            
        workspace_dir = os.path.join(project_dir, ".audit_workspace_v3")
        
        # Import and run orchestrate to set up workspace, audit_plan, etc.
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        init_plan_script = os.path.join(project_root, "src_v3", "cli", "init_plan.py")
        build_inv_script = os.path.join(project_root, "src_v3", "cli", "build_inventory.py")
        build_ir_script = os.path.join(project_root, "src_v3", "cli", "build_ir.py")
        build_index_script = os.path.join(project_root, "src_v3", "cli", "build_index.py")
        
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root
        
        # 1. Init plan
        subprocess.run([sys.executable, init_plan_script, "--project", project_dir], check=True, env=env)
        # 2. Build inventory
        subprocess.run([sys.executable, build_inv_script, "--workspace", workspace_dir], check=True, env=env)
        # 3. Build IR
        subprocess.run([sys.executable, build_ir_script, "--workspace", workspace_dir], check=True, env=env)
        
        # 4. First run of build_index.py (rebuilt should be 2, reused 0)
        proc = subprocess.run([sys.executable, build_index_script, "--workspace", workspace_dir], capture_output=True, text=True, check=True, env=env)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res["summary"]["rebuilt_count"], 2)
        self.assertEqual(res["summary"]["reused_count"], 0)
        self.assertEqual(res["summary"]["deleted_count"], 0)
        
        # 5. Second run of build_index.py (rebuilt should be 0, reused 2)
        proc = subprocess.run([sys.executable, build_index_script, "--workspace", workspace_dir], capture_output=True, text=True, check=True, env=env)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res["summary"]["rebuilt_count"], 0)
        self.assertEqual(res["summary"]["reused_count"], 2)
        self.assertEqual(res["summary"]["deleted_count"], 0)
        
        # 6. Modify one file (file1.py) and rebuild IR
        with open(os.path.join(project_dir, "file1.py"), "w") as f:
            f.write("def func1_modified():\n    pass\n")
        subprocess.run([sys.executable, build_ir_script, "--workspace", workspace_dir], check=True, env=env)
        
        # 7. Run build_index.py again (file1.py rebuilt, file2.py reused)
        proc = subprocess.run([sys.executable, build_index_script, "--workspace", workspace_dir], capture_output=True, text=True, check=True, env=env)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res["summary"]["rebuilt_count"], 1)
        self.assertEqual(res["summary"]["reused_count"], 1)
        self.assertEqual(res["summary"]["deleted_count"], 0)
        
        # 8. Delete file2.py, re-inventory & build IR
        os.unlink(os.path.join(project_dir, "file2.py"))
        subprocess.run([sys.executable, build_inv_script, "--workspace", workspace_dir], check=True, env=env)
        subprocess.run([sys.executable, build_ir_script, "--workspace", workspace_dir], check=True, env=env)
        
        # 9. Run build_index.py (file1.py reused, file2.py deleted from cache)
        proc = subprocess.run([sys.executable, build_index_script, "--workspace", workspace_dir], capture_output=True, text=True, check=True, env=env)
        res = json.loads(proc.stdout.strip())
        self.assertEqual(res["summary"]["rebuilt_count"], 0)
        self.assertEqual(res["summary"]["reused_count"], 1)
        self.assertEqual(res["summary"]["deleted_count"], 1)

if __name__ == "__main__":
    unittest.main()
