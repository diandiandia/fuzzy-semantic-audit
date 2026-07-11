import os
import json
from typing import Dict, Any, List
from src_v3.core.models import CandidateRecord, VerificationResult
from src_v3.storage.candidate_store import CandidateStore
from src_v3.storage.queue_store import QueueStore

class VerificationWriteback:
    """
    Coordinates candidate status writeback and queue updates.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.candidate_store = CandidateStore(self.workspace_dir)
        self.queue_store = QueueStore(self.workspace_dir)
        self.results_path = os.path.join(self.workspace_dir, "evidence", "verification_results.jsonl")

    def perform_writeback(
        self, 
        updated_candidates: List[CandidateRecord], 
        new_results: List[VerificationResult],
        manual_review_list: List[Dict[str, Any]],
        deferred_list: List[Dict[str, Any]]
    ) -> None:
        """
        Saves updated candidates, logs verification results, and flushes queues.
        """
        # 1. Overwrite pruned registry with final status updates
        self.candidate_store.upsert_candidates(updated_candidates, pruned=True)
        
        # 2. Append to verification_results.jsonl
        os.makedirs(os.path.dirname(self.results_path), exist_ok=True)
        with open(self.results_path, 'a', encoding='utf-8') as f:
            for res in new_results:
                f.write(json.dumps(res.to_dict(), ensure_ascii=False) + "\n")
                
        # 3. Clear queue verify_now.json
        self.queue_store.clear_verify_now()
        
        # 4. Deduplicate and save manual review & deferred queues
        def deduplicate_queue(q_list):
            seen = set()
            deduped = []
            for item in q_list:
                cid = item.get("candidate_id")
                if cid not in seen:
                    seen.add(cid)
                    deduped.append(item)
            return deduped

        self.queue_store.save_manual_review(deduplicate_queue(manual_review_list))
        self.queue_store.save_deferred(deduplicate_queue(deferred_list))
