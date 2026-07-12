import unittest
import os
import shutil
import tempfile
from src_v3.evidence.completeness import calculate_completeness_score, determine_evidence_gaps
from src_v3.evidence.assembler import assemble_evidence
from src_v3.core.models import CandidateRecord, IREdge, SymbolNode, TypeHint
from src_v3.storage.ir_store import IRStore

class TestEvidence(unittest.TestCase):
    def test_completeness_score(self):
        # 1. Base case: empty bundle
        bundle = {}
        score1 = calculate_completeness_score(bundle)
        self.assertEqual(score1, 10) # Base JID score

        # 2. Case with symbol body
        bundle2 = {"symbol_body": "def foo(): pass"}
        score2 = calculate_completeness_score(bundle2)
        self.assertEqual(score2, 40) # 10 + 30

        # 3. Case with full evidence
        bundle3 = {
            "symbol_body": "def foo(): pass",
            "caller_chain": [{"symbol": "bar"}],
            "upstream_entrypoints": [{"symbol": "api"}],
            "guard_snippets": [{"symbol": "guard"}],
            "resource_snippets": [{"symbol": "db"}],
            "state_transition_snippets": [{"symbol": "update"}]
        }
        score3 = calculate_completeness_score(bundle3)
        self.assertEqual(score3, 100) # Full completeness score (100)

    def test_determine_evidence_gaps(self):
        # 1. Empty bundle should flag gaps
        bundle = {}
        gaps = determine_evidence_gaps(bundle, ["authz"])
        self.assertTrue(any("missing symbol body" in g for g in gaps))
        self.assertTrue(any("missing authorization guard" in g for g in gaps))

        # 2. Complete bundle should have no gaps
        bundle_complete = {
            "symbol_body": "def foo(): pass",
            "caller_chain": [{"symbol": "bar"}],
            "upstream_entrypoints": [{"symbol": "api"}],
            "guard_snippets": [{"symbol": "guard"}]
        }
        gaps2 = determine_evidence_gaps(bundle_complete, ["authz"])
        self.assertEqual(len(gaps2), 0)

    def test_assembler_includes_type_hints(self):
        repo_dir = tempfile.mkdtemp()
        workspace_dir = os.path.join(repo_dir, ".audit_workspace_v3")
        try:
            with open(os.path.join(repo_dir, "app.py"), "w", encoding="utf-8") as source:
                source.write("def handle(user: User) -> User:\n    return user\n")
            store = IRStore(workspace_dir)
            store.save([
                SymbolNode("sym_app.py_handle_1_2", "symbol", "python", "app.py", "handle", {"start": 1, "end": 2}, {"symbol_kind": "function"}),
                TypeHint("hint_app.py_User_1_0", "type_hint", "python", "app.py", "User", {"start": 1, "end": 1}, {})
            ], [])
            candidate = CandidateRecord("cand", "key", "python-root", "python", "app.py", "handle", {"start": 1, "end": 2})
            bundle = assemble_evidence(workspace_dir, repo_dir, candidate, store)
            self.assertEqual(bundle.type_or_model_context[0]["symbol"], "User")
        finally:
            shutil.rmtree(repo_dir)

    def test_assembler_preserves_provider_and_framework_trace(self):
        repo_dir = tempfile.mkdtemp()
        workspace_dir = os.path.join(repo_dir, ".audit_workspace_v3")
        try:
            with open(os.path.join(repo_dir, "app.py"), "w", encoding="utf-8") as source:
                source.write("def entry():\n    handle()\n\ndef handle():\n    return query()\n")
            store = IRStore(workspace_dir)
            entry = SymbolNode(
                "sym_entry", "symbol", "python", "app.py", "entry", {"start": 1, "end": 2},
                {"framework_entrypoint": {
                    "route": "/api",
                    "provider_name": "ExpressPack",
                    "framework_trace": {"framework": "ExpressPack", "stage": "entrypoint"}
                }}
            )
            handle = SymbolNode(
                "sym_handle", "symbol", "python", "app.py", "handle", {"start": 4, "end": 5},
                {"framework_resource": {
                    "resource_type": "db",
                    "provider_name": "ExpressPack",
                    "framework_trace": {"framework": "ExpressPack", "stage": "resource"}
                }}
            )
            edge = IREdge("call_entry_handle", "call", "sym_entry", "sym_handle", provider_trace=["LSPProvider"])
            store.save([entry, handle], [edge])

            candidate = CandidateRecord(
                "cand", "key", "python-root", "python", "app.py", "handle", {"start": 4, "end": 5},
                provider_trace=["rule"]
            )
            bundle = assemble_evidence(workspace_dir, repo_dir, candidate, store)

            self.assertIn("rule", bundle.provider_trace)
            self.assertIn("LSPProvider", bundle.provider_trace)
            self.assertIn("ExpressPack", bundle.provider_trace)
            self.assertIn("provider_trace", bundle.caller_chain[0])
            self.assertEqual(bundle.resource_snippets[0]["framework_trace"]["stage"], "resource")
        finally:
            shutil.rmtree(repo_dir)

    def test_missing_candidate_symbol_has_explicit_gap_and_trace(self):
        workspace_dir = tempfile.mkdtemp()
        try:
            store = IRStore(workspace_dir)
            candidate = CandidateRecord(
                "missing", "key", "python-root", "python", "app.py", "absent", {"start": 1, "end": 1},
                provider_trace=["rule"]
            )
            bundle = assemble_evidence(workspace_dir, workspace_dir, candidate, store)
            self.assertEqual(bundle.provider_trace, ["rule"])
            self.assertIn("missing IR symbol node for candidate", bundle.evidence_gaps)
        finally:
            shutil.rmtree(workspace_dir)

if __name__ == "__main__":
    unittest.main()
