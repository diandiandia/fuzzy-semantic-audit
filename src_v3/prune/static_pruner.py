from typing import List, Dict, Any, Tuple
from src_v3.core.models import CandidateRecord
from src_v3.core.enums import CandidateStatus

def prune_candidates(
    candidates: List[CandidateRecord], 
    threshold: float = 45.0
) -> Tuple[List[CandidateRecord], Dict[str, Any]]:
    """
    Prunes candidates whose priority_score is below the threshold.
    Returns the list of kept candidates and pruning metrics.
    """
    recalled_total = len(candidates)
    kept_candidates = []
    
    for cand in candidates:
        if cand.priority_score >= threshold:
            # Transition status to pruned
            cand.status = CandidateStatus.PRUNED.value
            kept_candidates.append(cand)
            
    pruned_total = len(kept_candidates)
    compression_ratio = pruned_total / max(1, recalled_total)
    
    metrics = {
        "recalled_total": recalled_total,
        "pruned_total": pruned_total,
        "compression_ratio": compression_ratio,
        "compression_factor": recalled_total / max(1, pruned_total)
    }
    
    return kept_candidates, metrics
