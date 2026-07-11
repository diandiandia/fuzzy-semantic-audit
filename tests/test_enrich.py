import unittest
import os
import shutil
import tempfile
from src_v3.core.models import LanguageShard, IRNode, IREdge, SymbolNode, FileNode
from src_v3.storage.ir_store import IRStore
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.providers.semantic.base import SemanticProvider
from src_v3.enrich.framework_semantics import enrich_framework_semantics
from src_v3.enrich.semantic_orchestrator import enrich_semantic_relations

class MockFrameworkProvider(FrameworkProvider):
    framework_name: str = "MockFramework"

    def extract_entrypoints(self, ir_store):
        return [
            {
                "node_id": "sym_test_py_foo_1_10",
                "route": "/api/foo",
                "method": "GET",
                "confidence": 1.0
            }
        ]

    def extract_guards(self, ir_store):
        return [
            {
                "node_id": "sym_test_py_foo_1_10",
                "guard_kind": "role_check",
                "confidence": 0.9
            }
        ]

    def extract_resources(self, ir_store):
        return [
            {
                "node_id": "sym_test_py_foo_1_10",
                "resource_type": "database",
                "resource_details": "query_users"
            }
        ]

    def extract_state_transitions(self, ir_store):
        return [
            {
                "node_id": "sym_test_py_foo_1_10",
                "state_field": "status",
                "from_state": "pending",
                "to_state": "active"
            }
        ]

class MockSemanticProvider(SemanticProvider):
    provider_name: str = "MockSemantic"

    def capability_level(self) -> str:
        return "L2"

    def resolution_confidence(self) -> float:
        return 0.8

    def find_definitions(self, symbol_ref):
        return []

    def find_references(self, symbol_ref):
        return []

    def find_callers(self, symbol_ref):
        return [
            {
                "symbol": "caller_func",
                "file": "caller.py",
                "span": {"start": 5, "end": 15}
            }
        ]

    def find_callees(self, symbol_ref):
        return [
            {
                "symbol": "callee_func",
                "file": "callee.py",
                "span": {"start": 10, "end": 20}
            }
        ]

class TestEnrich(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_enrich_framework_semantics(self):
        ir_store = IRStore(self.tmp_dir)
        # Create a file node and a symbol node matching the mock provider node_id
        file_node = FileNode(node_id="file_test_py", kind="file", lang="python", file="test.py")
        sym_node = SymbolNode(
            node_id="sym_test_py_foo_1_10",
            kind="symbol",
            lang="python",
            file="test.py",
            symbol="foo",
            span={"start": 1, "end": 10},
            attributes={}
        )
        ir_store.save([file_node, sym_node], [], overwrite=True)

        shard = LanguageShard(shard_id="python-root", lang="python", paths=["test.py"])
        provider = MockFrameworkProvider()

        enrich_framework_semantics(self.tmp_dir, shard, [provider])

        # Verify updated attributes in symbol node
        symbols = ir_store.get_symbol_nodes()
        foo_node = next(s for s in symbols if s.symbol == "foo")
        self.assertIn("framework_entrypoint", foo_node.attributes)
        self.assertEqual(foo_node.attributes["framework_entrypoint"]["route"], "/api/foo")
        self.assertIn("framework_guard", foo_node.attributes)
        self.assertEqual(foo_node.attributes["framework_guard"]["guard_kind"], "role_check")
        self.assertIn("framework_resource", foo_node.attributes)
        self.assertEqual(foo_node.attributes["framework_resource"]["resource_details"], "query_users")
        self.assertIn("framework_state_transition", foo_node.attributes)
        self.assertEqual(foo_node.attributes["framework_state_transition"]["from_state"], "pending")

        # Verify new concrete nodes generated
        kinds = [s.kind for s in symbols]
        self.assertIn("guard_check", kinds)
        self.assertIn("resource_access", kinds)
        self.assertIn("state_transition", kinds)
        self.assertIn("entrypoint", kinds)

    def test_enrich_semantic_relations(self):
        ir_store = IRStore(self.tmp_dir)
        file_node = FileNode(node_id="file_test_py", kind="file", lang="python", file="test.py")
        sym_node = SymbolNode(
            node_id="sym_test_py_foo_1_10",
            kind="symbol",
            lang="python",
            file="test.py",
            symbol="foo",
            span={"start": 1, "end": 10},
            attributes={}
        )
        
        # Create caller and callee nodes so they match
        caller_node = SymbolNode(
            node_id="sym_caller_py_caller_func_5_15",
            kind="symbol",
            lang="python",
            file="caller.py",
            symbol="caller_func",
            span={"start": 5, "end": 15},
            attributes={}
        )
        
        callee_node = SymbolNode(
            node_id="sym_callee_py_callee_func_10_20",
            kind="symbol",
            lang="python",
            file="callee.py",
            symbol="callee_func",
            span={"start": 10, "end": 20},
            attributes={}
        )
        
        # Also add a fuzzy import edge
        import_edge = IREdge(
            edge_id="import_edge_1",
            kind="import",
            src_node_id="file_test_py",
            dst_node_id="import_callee"
        )
        
        callee_file_node = FileNode(
            node_id="file_callee_py",
            kind="file",
            lang="python",
            file="callee.py"
        )
        
        ir_store.save([file_node, sym_node, caller_node, callee_node, callee_file_node], [import_edge], overwrite=True)

        shard = LanguageShard(shard_id="python-root", lang="python", paths=["test.py"])
        semantic_provider = MockSemanticProvider()

        enrich_semantic_relations(self.tmp_dir, "repo_path", shard, semantic_provider)

        # Verify calling edges created
        edges = ir_store.get_edges()
        kinds = [e.kind for e in edges]
        self.assertIn("call", kinds)
        
        # Verify resolved import edge created
        self.assertIn("import_resolved", kinds)

if __name__ == "__main__":
    unittest.main()
