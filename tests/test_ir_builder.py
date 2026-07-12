import os
import shutil
import tempfile
import unittest

from src_v3.parse.ir_builder import build_file_ir
from src_v3.providers.parser.base import ParserProvider


class PartiallyFailingParser(ParserProvider):
    provider_name = "PartiallyFailingParser"

    def parse_file(self, file_path, lang):
        return {"mode": "mock"}

    def extract_symbols(self, tree, query_pack):
        return [{
            "symbol": "handle",
            "kind": "function",
            "span": {"start": 1, "end": 2},
            "attributes": {}
        }]

    def extract_imports(self, tree, query_pack):
        return []

    def extract_calls(self, tree, query_pack):
        raise RuntimeError("call extractor unavailable")

    def extract_type_hints(self, tree, query_pack):
        return []

    def extract_resources(self, tree, query_pack):
        raise ValueError("resource extractor unavailable")

    def extract_guards(self, tree, query_pack):
        return []

    def extract_states(self, tree, query_pack):
        return []

    def extract_entrypoints(self, tree, query_pack):
        return []

    def provider_version(self):
        return "test"

    def is_fallback_for_lang(self, lang):
        return False


class TestIRBuilder(unittest.TestCase):
    def setUp(self):
        self.repo_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.repo_dir)

    def test_partial_extraction_failures_are_visible_on_file_node(self):
        source_path = os.path.join(self.repo_dir, "app.py")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write("def handle():\n    return 1\n")

        nodes, edges = build_file_ir(source_path, self.repo_dir, "python", PartiallyFailingParser(), {})

        file_node = next(n for n in nodes if n.kind == "file")
        symbol_node = next(n for n in nodes if n.kind == "symbol")

        self.assertEqual(symbol_node.symbol, "handle")
        self.assertTrue(file_node.attributes["parse_partial"])
        self.assertEqual(
            [failure["stage"] for failure in file_node.attributes["extraction_failures"]],
            ["calls", "resources"]
        )
        self.assertTrue(any("calls" in reason for reason in file_node.attributes["degradation_reasons"]))
        self.assertTrue(any(edge.kind == "contain" for edge in edges))


if __name__ == "__main__":
    unittest.main()
