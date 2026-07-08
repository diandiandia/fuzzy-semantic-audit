from typing import Tuple, Dict, Any, Optional

def evaluate_verdict(
    votes: Dict[str, Any], 
    candidate_capability: Optional[str] = None, 
    run_capability: Optional[str] = None
) -> Tuple[str, str]:
    """
    Combines three-lens votes and capability levels into a final security verdict.
    Supported output states: verified, false_positive, needs_review, deferred, error.
    """
    reach = str(votes.get("reachability", "MAYBE")).upper()
    guard = str(votes.get("guarded", "MAYBE")).upper()
    exploit = str(votes.get("exploitability", "MAYBE")).upper()
    
    # 1. Processing or query errors -> Error state
    if "ERROR" in [reach, guard, exploit] or votes.get("error"):
        return "error", "Verification error occurred during referee lens query."
        
    # 2. Explicit deferral or capability-based deferral -> Deferred state
    if "DEFER" in [reach, guard, exploit] or "DEFERRED" in [reach, guard, exploit] or votes.get("deferred"):
        return "deferred", "Verification deferred by referee request."
        
    # If candidate requires L3 dynamic capabilities but run is degraded, defer verification
    if candidate_capability == "L3" and run_capability in ["L0", "L1", "L2"]:
        if reach == "MAYBE" or exploit == "MAYBE":
            return "deferred", f"Verification deferred: L3 candidate '{candidate_capability}' cannot be verified under degraded run capability '{run_capability}'."
            
    # 3. Blocked by guard or clearly unreachable/non-exploitable -> False Positive
    if reach == "NO" or exploit == "NO":
        return "false_positive", "Candidate is confirmed unreachable or non-exploitable by referee scan."
        
    if guard == "YES":
        return "false_positive", "Potential path exists but is fully blocked by active authorization guards."
        
    # 4. Confirmed reachable, unguarded, and exploitable -> Verified Vulnerability
    if reach == "YES" and guard == "NO" and exploit == "YES":
        return "verified", "Reachable, unguarded, and exploitable code path confirmed by all lenses."
        
    # 5. Everything else -> Needs Manual Review
    return "needs_review", f"Indeterminate status (Reachability: {reach}, Guarded: {guard}, Exploitability: {exploit}). Requires manual triage."
