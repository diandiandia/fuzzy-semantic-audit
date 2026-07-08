from typing import Dict, Any

def calculate_completeness_score(bundle: Dict[str, Any]) -> int:
    """
    Calculates the evidence completeness score (0-100) based on loaded evidence segments.
    0-30: Text or rule hit only
    31-60: Has structural context (symbol body)
    61-80: Has call chain or resource chain
    81-100: Has entrypoints, guards, resources, and state machine core evidence
    """
    score = 10 # Base score for rule hit
    
    # 1. Structural context
    if bundle.get("symbol_body"):
        score += 30
        
    # 2. Connection chain context
    has_chains = False
    if bundle.get("caller_chain") or bundle.get("callee_chain"):
        score += 20
        has_chains = True
        
    # 3. Core semantic components (up to 40 points)
    if bundle.get("upstream_entrypoints"):
        score += 10
    if bundle.get("guard_snippets"):
        score += 10
    if bundle.get("resource_snippets"):
        score += 10
    if bundle.get("state_transition_snippets"):
        score += 10
        
    return min(100, score)
