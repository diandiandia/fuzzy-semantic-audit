from typing import Dict, Any

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

def calculate_priority_score(features: Dict[str, float], config: Dict[str, Any]) -> float:
    """
    Computes priority_score as a weighted sum of characteristic features
    and applies path weight decay multipliers.
    """
    weights = config.get("scoring_weights", DEFAULT_WEIGHTS)
    
    score = 0.0
    for name, value in features.items():
        if name == "path_decay_factor":
            continue
        weight = weights.get(name, DEFAULT_WEIGHTS.get(name, 0.0))
        score += value * weight
        
    decay_factor = features.get("path_decay_factor", 1.0)
    final_score = score * 100.0 * decay_factor
    
    return min(100.0, max(0.0, final_score))
