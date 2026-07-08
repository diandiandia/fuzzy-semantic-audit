import unittest
import os
import shutil
import tempfile
from src_v3.core.models import IRNode, IREdge, CandidateRecord
from src_v3.storage.ir_store import IRStore
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.index_store import IndexStore

class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_ir_store(self):
        store = IRStore(self.tmp_dir)
        
        file_node = IRNode(node_id="file_1", kind="file", lang="python", file="test.py")
        sym_node = IRNode(node_id="sym_1", kind="symbol", lang="python", file="test.py", symbol="foo")
        edge = IREdge(edge_id="e_1", kind="call", src_node_id="sym_1", dst_node_id="sym_2")
        
        store.save([file_node, sym_node], [edge], overwrite=True)
        
        file_nodes = store.get_file_nodes()
        self.assertEqual(len(file_nodes), 1)
        self.assertEqual(file_nodes[0].node_id, "file_1")
        
        sym_nodes = store.get_symbols_by_file("test.py")
        self.assertEqual(len(sym_nodes), 1)
        self.assertEqual(sym_nodes[0].symbol, "foo")
        
        edges = store.get_edges()
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].edge_id, "e_1")

    def test_candidate_store(self):
        store = CandidateStore(self.tmp_dir)
        
        cand = CandidateRecord(
            candidate_id="cand_1",
            identity_key="k1",
            shard_id="python-root",
            lang="python",
            file="main.py",
            symbol="run",
            span={"start": 1, "end": 10},
            source_tracks=["authz"],
            matched_rules=["r1"],
            recall_sources=["rule"],
            provider_trace=["p1"],
            priority_score=50.0,
            candidate_capability="L1",
            status="discovered"
        )
        
        store.save_candidates([cand], pruned=False, overwrite=True)
        
        cands = store.get_candidates(pruned=False)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].candidate_id, "cand_1")
        self.assertEqual(cands[0].status, "discovered")
        
        # Test status querying
        results = store.get_candidates_by_status("discovered", pruned=False)
        self.assertEqual(len(results), 1)

    def test_index_store(self):
        store = IndexStore(self.tmp_dir)
        store.register_index("python-root", "semantic", "indexed", "/path/to/idx", {"test": "meta"})
        
        status = store.get_index_status("python-root")
        self.assertEqual(status["semantic"]["status"], "indexed")
        self.assertEqual(status["semantic"]["metadata"]["test"], "meta")

if __name__ == "__main__":
    unittest.main()
