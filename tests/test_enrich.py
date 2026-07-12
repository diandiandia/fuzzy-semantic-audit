import unittest
import os
import shutil
import tempfile
from src_v3.core.models import AuditPlan, LanguageShard, IRNode, IREdge, SymbolNode, FileNode
from src_v3.core.plan_io import save_plan
from src_v3.storage.ir_store import IRStore
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.providers.framework.django import DjangoPack
from src_v3.providers.framework.express import ExpressPack
from src_v3.providers.framework.gin import GinPack
from src_v3.providers.framework.spring import SpringPack
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

    def test_framework_provider_uses_source_context_for_route_and_trace(self):
        root_dir = tempfile.mkdtemp()
        try:
            repo_dir = os.path.join(root_dir, "repo")
            workspace_dir = os.path.join(root_dir, "workspace")
            os.makedirs(repo_dir, exist_ok=True)
            os.makedirs(workspace_dir, exist_ok=True)
            with open(os.path.join(repo_dir, "routes.js"), "w", encoding="utf-8") as f:
                f.write("router.post('/pay', requireAuth, pay)\nfunction pay(req, res) {\n  db.query('select 1')\n}\n")

            save_plan(AuditPlan(
                version="3",
                repo_path=repo_dir,
                workspace_dir=workspace_dir,
                repo_profile_path="repo_profile.json"
            ), os.path.join(workspace_dir, "audit_plan.json"))

            ir_store = IRStore(workspace_dir)
            file_node = FileNode(node_id="file_routes_js", kind="file", lang="javascript", file="routes.js")
            sym_node = SymbolNode(
                node_id="sym_routes_js_pay_2_4",
                kind="symbol",
                lang="javascript",
                file="routes.js",
                symbol="pay",
                span={"start": 2, "end": 4},
                attributes={}
            )
            ir_store.save([file_node, sym_node], [], overwrite=True)

            shard = LanguageShard(shard_id="javascript-root", lang="javascript", paths=["routes.js"])
            enrich_framework_semantics(workspace_dir, shard, [ExpressPack()])

            enriched = IRStore(workspace_dir).get_node_by_id("sym_routes_js_pay_2_4")
            entrypoint = enriched.attributes["framework_entrypoint"]
            guard = enriched.attributes["framework_guard"]
            resource = enriched.attributes["framework_resource"]

            self.assertEqual(entrypoint["route"], "/pay")
            self.assertEqual(entrypoint["method"], "POST")
            self.assertEqual(entrypoint["framework_trace"]["framework"], "ExpressPack")
            self.assertTrue(guard["framework_trace"]["details"]["matched_context"])
            self.assertTrue(resource["framework_trace"]["details"]["matched_context"])
        finally:
            shutil.rmtree(root_dir)

    def test_first_framework_packs_extract_multiple_semantic_categories(self):
        cases = [
            (
                DjangoPack(),
                "views.py",
                "@login_required\ndef api_view(request):\n    return User.objects.filter(active=True)\n",
                "api_view",
                {"start": 2, "end": 3}
            ),
            (
                GinPack(),
                "handlers.go",
                "r.GET('/orders', AuthMiddleware(), ListOrders)\nfunc ListOrders(c *gin.Context) {\n    db.Find(&orders)\n    c.JSON(200, orders)\n}\n",
                "ListOrders",
                {"start": 2, "end": 5}
            ),
            (
                SpringPack(),
                "OrderController.java",
                "@GetMapping('/orders')\n@PreAuthorize(\"hasRole('ADMIN')\")\npublic List<Order> orders() {\n    return orderRepository.findAll();\n}\n",
                "orders",
                {"start": 3, "end": 5}
            )
        ]

        for provider, rel_file, content, symbol, span in cases:
            with self.subTest(provider=provider.framework_name):
                root_dir = tempfile.mkdtemp()
                try:
                    repo_dir = os.path.join(root_dir, "repo")
                    workspace_dir = os.path.join(root_dir, "workspace")
                    os.makedirs(repo_dir, exist_ok=True)
                    os.makedirs(workspace_dir, exist_ok=True)
                    with open(os.path.join(repo_dir, rel_file), "w", encoding="utf-8") as f:
                        f.write(content)
                    save_plan(AuditPlan(
                        version="3",
                        repo_path=repo_dir,
                        workspace_dir=workspace_dir,
                        repo_profile_path="repo_profile.json"
                    ), os.path.join(workspace_dir, "audit_plan.json"))

                    ir_store = IRStore(workspace_dir)
                    file_node = FileNode(node_id=f"file_{provider.framework_name}", kind="file", lang="mixed", file=rel_file)
                    sym_node = SymbolNode(
                        node_id=f"sym_{provider.framework_name}",
                        kind="symbol",
                        lang="mixed",
                        file=rel_file,
                        symbol=symbol,
                        span=span,
                        attributes={}
                    )
                    ir_store.save([file_node, sym_node], [], overwrite=True)

                    entrypoints = provider.extract_entrypoints(ir_store)
                    guards = provider.extract_guards(ir_store)
                    resources = provider.extract_resources(ir_store)
                    categories = sum(bool(items) for items in [entrypoints, guards, resources])

                    self.assertGreaterEqual(categories, 2)
                    if entrypoints:
                        self.assertEqual(entrypoints[0]["framework_trace"]["framework"], provider.framework_name)
                finally:
                    shutil.rmtree(root_dir)

if __name__ == "__main__":
    unittest.main()
