from typing import Tuple, Dict, Any, Optional

def evaluate_verdict(
    votes: Dict[str, Any], 
    candidate_capability: Optional[str] = None, 
    run_capability: Optional[str] = None
) -> Tuple[str, str]:
    """
    Combines three-lens votes and capability levels into a final security verdict.
    Supported output states: verified, false_positive, needs_review, deferred, error.
    
    Lenses:
    - reachability: YES / NO / MAYBE
    - guarded: YES / NO / PARTIAL / MAYBE
    - exploitability: YES / NO / MAYBE
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
        
    # 3. Capability-based verification check (degradation awareness)
    # Check if run capability is sufficient to verify the candidate capability.
    cap_levels = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
    cand_level = cap_levels.get(candidate_capability or "L0", 0)
    run_level = cap_levels.get(run_capability or "L0", 0)
    
    if run_level < cand_level:
        # If run is degraded and referee votes are not definitive, we must defer to avoid false positives/negatives
        if "MAYBE" in [reach, guard, exploit] or guard == "PARTIAL":
            return "deferred", f"Verification deferred: Candidate capability '{candidate_capability}' exceeds run capability '{run_capability}', and referee votes are indeterminate."
            
    # 4. Blocked by guard or clearly unreachable/non-exploitable -> False Positive
    if reach == "NO" or exploit == "NO":
        return "false_positive", "Candidate is confirmed unreachable or non-exploitable by referee scan."
        
    if guard == "YES":
        return "false_positive", "Potential path exists but is fully blocked by active authorization guards."
        
    # 5. Confirmed reachable, unguarded, and exploitable -> Verified Vulnerability
    if reach == "YES" and guard == "NO" and exploit == "YES":
        return "verified", "Reachable, unguarded, and exploitable code path confirmed by all lenses."
        
    # 6. Everything else -> Needs Manual Review
    return "needs_review", f"Indeterminate status (Reachability: {reach}, Guarded: {guard}, Exploitability: {exploit}). Requires manual triage."
