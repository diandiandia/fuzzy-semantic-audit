from typing import List, Dict, Any, Tuple, Set
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
    dropped_candidates = []
    
    for cand in candidates:
        if cand.priority_score >= threshold:
            # Transition status to pruned
            cand.status = CandidateStatus.PRUNED.value
            kept_candidates.append(cand)
        else:
            dropped_candidates.append(cand)
            
    pruned_total = len(kept_candidates)
    dropped_total = len(dropped_candidates)
    compression_ratio = pruned_total / max(1, recalled_total)
    
    metrics = {
        "recalled_total": recalled_total,
        "pruned_total": pruned_total,
        "dropped_total": dropped_total,
        "compression_ratio": compression_ratio,
        "compression_factor": recalled_total / max(1, pruned_total),
        "threshold": threshold,
        "kept_ids": [cand.candidate_id for cand in kept_candidates],
        "dropped_ids": [cand.candidate_id for cand in dropped_candidates],
        "status_counts": {
            CandidateStatus.PRUNED.value: pruned_total,
            "dropped_by_pruner": dropped_total
        }
    }
    
    return kept_candidates, metrics

def evaluate_pruning_against_labels(
    candidates: List[CandidateRecord],
    expected_keep_ids: Set[str],
    threshold: float = 45.0
) -> Dict[str, Any]:
    """
    Deterministic local evaluation helper for golden pruning fixtures.
    It does not assign vulnerability truth; it only checks whether static
    pruning preserves the candidates that a fixture says must reach triage.
    """
    kept, metrics = prune_candidates(candidates, threshold=threshold)
    kept_ids = {cand.candidate_id for cand in kept}
    dropped_ids = {cand.candidate_id for cand in candidates} - kept_ids
    true_positive_kept = kept_ids & expected_keep_ids
    false_drop_ids = expected_keep_ids & dropped_ids
    unexpected_keep_ids = kept_ids - expected_keep_ids

    return {
        **metrics,
        "expected_keep_total": len(expected_keep_ids),
        "fixture_recall": len(true_positive_kept) / max(1, len(expected_keep_ids)),
        "unexpected_keep_total": len(unexpected_keep_ids),
        "false_drop_total": len(false_drop_ids),
        "false_drop_ids": sorted(false_drop_ids),
        "unexpected_keep_ids": sorted(unexpected_keep_ids)
    }
