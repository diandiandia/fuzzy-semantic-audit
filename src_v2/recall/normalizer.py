from typing import List, Dict
from src_v2.core.models import CandidateRecord, Span
from src_v2.core.candidate_registry import make_identity_key, make_candidate_id

def normalize_candidates(raw_records: List[CandidateRecord]) -> List[CandidateRecord]:
    """Merge duplicate candidates by identity_key and sort them by priority descending."""
    merged_map: Dict[str, CandidateRecord] = {}
    
    for c in raw_records:
        # Re-verify and ensure identity key and ID are set correctly
        start = c.span.start
        end = c.span.end
        c.identity_key = make_identity_key(c.shard_id, c.file, c.symbol, start, end)
        c.candidate_id = make_candidate_id(c.shard_id, c.file, c.symbol, start, end)
        
        key = c.identity_key
        if key in merged_map:
            old = merged_map[key]
            # Merge lists
            old.source_tracks = sorted(list(set(old.source_tracks + c.source_tracks)))
            old.matched_rules = sorted(list(set(old.matched_rules + c.matched_rules)))
            old.recall_sources = sorted(list(set(old.recall_sources + c.recall_sources)))
            old.priority = max(old.priority, c.priority)
        else:
            merged_map[key] = c
            
    # Convert back to list and sort by priority descending
    normalized = list(merged_map.values())
    normalized.sort(key=lambda x: x.priority, reverse=True)
    return normalized
