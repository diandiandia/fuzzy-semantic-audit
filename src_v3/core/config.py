from typing import Dict, Any

DEFAULT_CONFIG = {
    "semantic_preference": ["lsp", "lsif", "codegraph", "ctags", "null"],
    "parser_preference": "native",
    "embedding_preference": "keyword",
    "scoring_weights": {
        "signal_score": 0.15,
        "semantic_similarity_score": 0.15,
        "reachability_score": 0.15,
        "guard_conflict_score": 0.10,
        "framework_risk_score": 0.15,
        "code_quality_score": 0.05,
        "path_relevance_score": 0.10,
        "parameter_propagation_score": 0.15
    }
}

def get_config(plan_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts config and overlays with DEFAULT_CONFIG.
    """
    config = plan_summary.get("config", {})
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged
