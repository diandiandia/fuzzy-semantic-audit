import os
import unittest
import tempfile
import json
from unittest.mock import patch
from src_v4.packs.dynamic_packer import AIDynamicPacker

class TestAIDynamicPacker(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name
        self.packer = AIDynamicPacker()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_generate_pack_fallback(self):
        # By default, without environment variables, it should fallback to static rules
        with patch.dict(os.environ, {}, clear=True):
            pack = self.packer.generate_pack(["java", "cpp"], self.repo_path)
            
            self.assertEqual(pack["scanned_languages"], ["java", "cpp"])
            self.assertIn("java", pack["rules"])
            self.assertIn("cpp", pack["rules"])
            
            # Check fallback fields
            self.assertTrue(len(pack["rules"]["java"]["keywords"]) > 0)
            self.assertTrue(len(pack["rules"]["java"]["regex_patterns"]) > 0)
            self.assertTrue(len(pack["rules"]["java"]["ast_queries"]) > 0)
            
            # Check file persistence
            pack_json_path = os.path.join(self.repo_path, "scan_pack.json")
            self.assertTrue(os.path.exists(pack_json_path))
            with open(pack_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertIn("java", data["rules"])

    @patch("src_v4.packs.dynamic_packer.query_llm")
    def test_generate_pack_llm_success(self, mock_query):
        # Mock LLM API response
        mock_response = json.dumps({
            "keywords": ["testAPI", "dangerousFunc"],
            "regex_patterns": ["testAPI\\("],
            "ast_queries": ["(test_query)"]
        })
        mock_query.return_value = mock_response
        
        pack = self.packer.generate_pack(["java"], self.repo_path)
        
        self.assertEqual(pack["scanned_languages"], ["java"])
        self.assertIn("testAPI", pack["rules"]["java"]["keywords"])
        self.assertIn("(test_query)", pack["rules"]["java"]["ast_queries"])
        
        # Verify interpolation template is also added
        # Check that we have a query containing testAPI
        found_interpolated = False
        for q in pack["rules"]["java"]["ast_queries"]:
            if "testAPI" in q:
                found_interpolated = True
                break
        self.assertTrue(found_interpolated)

if __name__ == "__main__":
    unittest.main()
