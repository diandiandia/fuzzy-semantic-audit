from typing import Dict, Any

DEFAULT_WEIGHTS = {
    "signal_score": 0.25,
    "semantic_similarity_score": 0.20,
    "reachability_score": 0.20,
    "guard_conflict_score": 0.15,
    "framework_risk_score": 0.10,
    "code_quality_score": 0.10
}

def calculate_priority_score(features: Dict[str, float], config: Dict[str, Any]) -> float:
    """
    Computes priority_score as a weighted sum of characteristic features.
    """
    weights = config.get("scoring_weights", DEFAULT_WEIGHTS)
    
    score = 0.0
    for name, value in features.items():
        weight = weights.get(name, DEFAULT_WEIGHTS.get(name, 0.0))
        score += value * weight
        
    return min(100.0, max(0.0, score * 100.0))
