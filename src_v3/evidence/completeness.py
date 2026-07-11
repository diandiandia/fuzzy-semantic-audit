from typing import Dict, Any, List

def calculate_completeness_score(bundle: Dict[str, Any], source_tracks: List[str] = None) -> int:
    """
    Calculates the evidence completeness score (0-100) based on loaded evidence segments
    and track-specific requirements.
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
    has_ep = bool(bundle.get("upstream_entrypoints"))
    has_gd = bool(bundle.get("guard_snippets"))
    has_res = bool(bundle.get("resource_snippets"))
    has_st = bool(bundle.get("state_transition_snippets"))
    
    if has_ep:
        score += 10
    if has_gd:
        score += 10
    if has_res:
        score += 10
    if has_st:
        score += 10
        
    # 4. Track-specific requirements & bonuses (up to 10 points bonus)
    if source_tracks:
        for track in source_tracks:
            # authz needs guards & entrypoints
            if track == "authz":
                if has_gd and has_ep:
                    score += 10 # Complete authz path verified
                elif not has_gd:
                    score -= 5 # Missing guard context
            # injection needs entrypoints (input source) & resource access (db/process sink)
            elif track == "injection":
                if has_ep and has_res:
                    score += 10 # Complete input-to-sink path verified
                elif not has_res:
                    score -= 5 # Missing sink context
            # state_machine needs state transition & guard context
            elif track == "state_machine":
                if has_st and has_gd:
                    score += 10
            # resource_access needs resource access context
            elif track == "resource_access":
                if has_res:
                    score += 10
                    
    return min(100, max(10, score))

def determine_evidence_gaps(bundle: Dict[str, Any], source_tracks: List[str] = None) -> List[str]:
    """
    Identifies missing elements in the evidence bundle based on the source tracks.
    """
    gaps = []
    if not bundle.get("symbol_body"):
        gaps.append("missing symbol body structural context")
    if not bundle.get("caller_chain") and not bundle.get("callee_chain"):
        gaps.append("missing connection chain context")
        
    has_ep = bool(bundle.get("upstream_entrypoints"))
    has_gd = bool(bundle.get("guard_snippets"))
    has_res = bool(bundle.get("resource_snippets"))
    has_st = bool(bundle.get("state_transition_snippets"))
    
    if source_tracks:
        for track in source_tracks:
            if track == "authz":
                if not has_gd:
                    gaps.append("authz track requirement gap: missing authorization guard snippet")
                if not has_ep:
                    gaps.append("authz track requirement gap: missing reachability entrypoint")
            elif track == "injection":
                if not has_ep:
                    gaps.append("injection track requirement gap: missing input source entrypoint")
                if not has_res:
                    gaps.append("injection track requirement gap: missing database/process resource sink")
            elif track == "state_machine":
                if not has_st:
                    gaps.append("state_machine track requirement gap: missing state transition trigger")
                if not has_gd:
                    gaps.append("state_machine track requirement gap: missing guard validation snippet")
            elif track == "resource_access":
                if not has_res:
                    gaps.append("resource_access track requirement gap: missing resource access snippet")
                    
    return gaps
