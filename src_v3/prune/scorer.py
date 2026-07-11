from typing import Dict, Any, List

DEFAULT_WEIGHTS = {
    "signal_score": 0.15,
    "semantic_similarity_score": 0.15,
    "reachability_score": 0.15,
    "guard_conflict_score": 0.10,
    "framework_risk_score": 0.15,
    "code_quality_score": 0.05,
    "path_relevance_score": 0.10,
    "parameter_propagation_score": 0.15
}

def calculate_priority_score(
    features: Dict[str, float], 
    config: Dict[str, Any], 
    source_tracks: List[str] = None
) -> float:
    """
    Computes priority_score as a weighted sum of characteristic features,
    dynamically adjusting weights based on target tracks,
    and applies path weight decay multipliers.
    """
    base_weights = dict(config.get("scoring_weights", DEFAULT_WEIGHTS))
    
    # Track-specific dynamic weights refinement
    if source_tracks:
        for track in source_tracks:
            if track == "authz":
                # Missing guards and reachability are critical for authorization
                base_weights["guard_conflict_score"] = 0.25
                base_weights["reachability_score"] = 0.20
                base_weights["semantic_similarity_score"] = 0.10
            elif track == "injection":
                # Parameter propagation and sink reachability are critical for injection
                base_weights["parameter_propagation_score"] = 0.25
                base_weights["reachability_score"] = 0.20
                base_weights["guard_conflict_score"] = 0.05
            elif track == "state_machine":
                # State transition risk and framework risk are critical
                base_weights["framework_risk_score"] = 0.25
                base_weights["guard_conflict_score"] = 0.15
                
    # Normalize weights so they sum to 1.0 (excluding path_decay_factor)
    total_w = sum(w for k, w in base_weights.items())
    if total_w > 0:
        weights = {k: w / total_w for k, w in base_weights.items()}
    else:
        weights = DEFAULT_WEIGHTS
    
    score = 0.0
    for name, value in features.items():
        if name == "path_decay_factor":
            continue
        weight = weights.get(name, 0.0)
        score += value * weight
        
    decay_factor = features.get("path_decay_factor", 1.0)
    final_score = score * 100.0 * decay_factor
    
    return min(100.0, max(0.0, final_score))
