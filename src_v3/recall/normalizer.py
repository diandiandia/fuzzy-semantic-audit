import re
from typing import List, Dict, Any
from src_v3.core.models import CandidateRecord
from src_v3.core.enums import CapabilityLevel

def normalize_node_id(text: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', text)

def compare_capability(cap1: str, cap2: str) -> str:
    """
    Returns the higher capability level of the two.
    """
    levels = {CapabilityLevel.L0: 0, CapabilityLevel.L1: 1, CapabilityLevel.L2: 2, CapabilityLevel.L3: 3}
    v1 = levels.get(CapabilityLevel(cap1), 0) if cap1 in levels else 0
    v2 = levels.get(CapabilityLevel(cap2), 0) if cap2 in levels else 0
    return cap1 if v1 >= v2 else cap2

def normalize_candidates(candidates: List[CandidateRecord]) -> List[CandidateRecord]:
    """
    Deduplicates and merges candidate records from different recall channels.
    Deduplication key: (shard_id, file, symbol, span.start, span.end)
    """
    merged: Dict[str, CandidateRecord] = {}
    
    for cand in candidates:
        key = f"{cand.shard_id}|{cand.file}|{cand.symbol}|{cand.span.get('start', 0)}|{cand.span.get('end', 0)}"
        cand.identity_key = key
        
        if key not in merged:
            # Create a copy/new record to avoid modifying in-place unexpectedly
            merged[key] = CandidateRecord(
                candidate_id=f"cand_{normalize_node_id(key)}",
                identity_key=key,
                shard_id=cand.shard_id,
                lang=cand.lang,
                file=cand.file,
                symbol=cand.symbol,
                span=cand.span,
                source_tracks=list(set(cand.source_tracks)),
                matched_rules=list(set(cand.matched_rules)),
                recall_sources=list(set(cand.recall_sources)),
                provider_trace=list(set(cand.provider_trace)),
                priority_score=cand.priority_score,
                candidate_capability=cand.candidate_capability,
                status=cand.status
            )
        else:
            existing = merged[key]
            # Merge lists
            existing.source_tracks = list(set(existing.source_tracks + cand.source_tracks))
            existing.matched_rules = list(set(existing.matched_rules + cand.matched_rules))
            existing.recall_sources = list(set(existing.recall_sources + cand.recall_sources))
            existing.provider_trace = list(set(existing.provider_trace + cand.provider_trace))
            # Take max priority score
            existing.priority_score = max(existing.priority_score, cand.priority_score)
            # Take highest capability level
            existing.candidate_capability = compare_capability(existing.candidate_capability, cand.candidate_capability)
            
    return list(merged.values())
