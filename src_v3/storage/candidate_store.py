import os
import json
from typing import List, Generator, Optional
from src_v3.core.models import CandidateRecord

class CandidateStore:
    """
    Handles storage of CandidateRecords under .audit_workspace_v3/candidates/.
    Supports querying and registry updates.
    """
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.candidates_dir = os.path.join(self.workspace_dir, "candidates")
        os.makedirs(self.candidates_dir, exist_ok=True)
        
        self.registry_path = os.path.join(self.candidates_dir, "candidate_registry.jsonl")
        self.pruned_path = os.path.join(self.candidates_dir, "pruned_registry.jsonl")

    def save_candidates(self, candidates: List[CandidateRecord], pruned: bool = False, overwrite: bool = True) -> None:
        """
        Saves candidate records to the respective registry JSONL file.
        Deduplicates and merges candidates on overwrite by identity_key.
        """
        path = self.pruned_path if pruned else self.registry_path
        
        if overwrite:
            merged = {}
            for cand in candidates:
                key = cand.candidate_id if cand.candidate_id else cand.identity_key
                if key not in merged:
                    merged[key] = cand
                else:
                    existing = merged[key]
                    existing.source_tracks = sorted(list(set(existing.source_tracks + cand.source_tracks)))
                    existing.matched_rules = sorted(list(set(existing.matched_rules + cand.matched_rules)))
                    existing.recall_sources = sorted(list(set(existing.recall_sources + cand.recall_sources)))
                    existing.provider_trace = sorted(list(set(existing.provider_trace + cand.provider_trace)))
                    existing.priority_score = max(existing.priority_score, cand.priority_score)
                    existing.evidence_refs = sorted(list(set(existing.evidence_refs + cand.evidence_refs)))
                    
                    cap_vals = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
                    max_cap = max(cap_vals.get(existing.candidate_capability, 0), cap_vals.get(cand.candidate_capability, 0))
                    inv_cap = {0: "L0", 1: "L1", 2: "L2", 3: "L3"}
                    existing.candidate_capability = inv_cap[max_cap]
                    
            candidates_to_save = list(merged.values())
            mode = 'w'
        else:
            candidates_to_save = candidates
            mode = 'a'
            
        with open(path, mode, encoding='utf-8') as f:
            for cand in candidates_to_save:
                f.write(json.dumps(cand.to_dict(), ensure_ascii=False) + "\n")

    def upsert_candidates(self, candidates: List[CandidateRecord], pruned: bool = False) -> None:
        """
        Safely updates existing candidates by candidate_id or identity_key, 
        preserving all other records in the registry file without data loss.
        """
        existing = self.get_candidates(pruned=pruned)
        existing_map = {}
        for cand in existing:
            key = cand.candidate_id if cand.candidate_id else cand.identity_key
            existing_map[key] = cand
            
        for cand in candidates:
            key = cand.candidate_id if cand.candidate_id else cand.identity_key
            existing_map[key] = cand
            
        self.save_candidates(list(existing_map.values()), pruned=pruned, overwrite=True)

    def get_candidates(self, pruned: bool = False) -> List[CandidateRecord]:
        """
        Loads and returns all candidates in the registry.
        """
        return list(self.iter_candidates(pruned))

    def iter_candidates(self, pruned: bool = False) -> Generator[CandidateRecord, None, None]:
        path = self.pruned_path if pruned else self.registry_path
        if not os.path.exists(path):
            return
            
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    yield CandidateRecord.from_dict(json.loads(line.strip()))

    def get_candidates_by_status(self, status: str, pruned: bool = False) -> List[CandidateRecord]:
        """
        Filters candidates by their status.
        """
        results = []
        for cand in self.iter_candidates(pruned):
            if cand.status == status:
                results.append(cand)
        return results

    def get_candidates_by_shard(self, shard_id: str, pruned: bool = False) -> List[CandidateRecord]:
        """
        Filters candidates by shard.
        """
        results = []
        for cand in self.iter_candidates(pruned):
            if cand.shard_id == shard_id:
                results.append(cand)
        return results

    def get_candidate_by_id(self, candidate_id: str, pruned: bool = False) -> Optional[CandidateRecord]:
        """
        Locates a single candidate by its ID.
        """
        for cand in self.iter_candidates(pruned):
            if cand.candidate_id == candidate_id:
                return cand
        return None
