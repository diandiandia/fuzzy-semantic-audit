from typing import List, Optional
from src_v2.core.models import CandidateRecord, RepoProfile

def rank_priority(candidate: CandidateRecord, profile: Optional[RepoProfile] = None) -> int:
    """Calculate and return a priority score (0-100) for a candidate."""
    score = 30  # Baseline
    
    # 1. Track priority weights
    track_weights = {
        "authz": 25,
        "injection": 25,
        "memory_safety": 20,
        "state_machine": 15,
        "deserialization": 15,
        "resource_access": 10,
        "filesystem_boundary": 10,
        "input_validation": 5,
        "concurrency": 5,
        "crypto": 5
    }
    for track in candidate.source_tracks:
        score += track_weights.get(track, 5)
        
    # 2. Match rules count bonus
    score += len(candidate.matched_rules) * 10
    
    # 3. Recall sources count bonus
    score += len(candidate.recall_sources) * 5
    
    # 4. Entrypoint proximity bonus
    if profile and profile.entrypoint_hints:
        # If candidate file is in entrypoints, give large bonus
        if any(c_file in entry for entry in profile.entrypoint_hints for c_file in [candidate.file]):
            score += 20
        # If file path contains terms like "api", "route", "controller", "handler"
        path_lower = candidate.file.lower()
        if any(kw in path_lower for kw in ["api", "route", "controller", "handler", "server", "web"]):
            score += 15
            
    # Cap between 1 and 100
    return max(1, min(100, score))

def rank_candidates(candidates: List[CandidateRecord], profile: Optional[RepoProfile] = None) -> List[CandidateRecord]:
    """Calculate priority for a list of candidates and sort them."""
    for c in candidates:
        c.priority = rank_priority(c, profile)
    candidates.sort(key=lambda x: x.priority, reverse=True)
    return candidates
