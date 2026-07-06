from typing import List, Dict, Tuple

def decide(votes: List[Dict[str, str]]) -> Tuple[str, str]:
    """
    Decide the final verdict and summary reason from referee votes.
    Returns (verdict, reason).
    """
    if not votes:
        return "needs_review", "No referee votes received."
        
    vote_map = {v.get("lens"): v for v in votes}
    
    reach = vote_map.get("reachability")
    guard = vote_map.get("guard")
    exploit = vote_map.get("exploit")
    
    # Extract decisions
    reach_decision = reach.get("decision") if reach else "uncertain"
    guard_decision = guard.get("decision") if guard else "uncertain"
    exploit_decision = exploit.get("decision") if exploit else "uncertain"
    
    # 1. Verified condition: reachability, guard bypass, and exploitability are all confirmed (pass)
    if reach_decision == "pass" and guard_decision == "pass" and exploit_decision == "pass":
        reason = "Confirmed: Path is reachable, guards are absent/bypassable, and code is exploitable."
        return "verified", reason
        
    # 2. False Positive condition: if all referees agree it is safe (fail), or if reachability is explicitly falsified
    # and guard/exploit are also falsified.
    if reach_decision == "fail" and guard_decision == "fail" and exploit_decision == "fail":
        reason = "Excluded: All lenses falsified the vulnerability (unreachable, valid guards, not exploitable)."
        return "false_positive", reason
        
    # Standard logic: if reachability is completely false, but maybe others are uncertain/pass,
    # or if guard is completely valid (fail) and exploit is safe (fail):
    if (reach_decision == "fail" and guard_decision == "fail") or (guard_decision == "fail" and exploit_decision == "fail"):
        reason = "Excluded: Main validation lenses confirm no vulnerability."
        return "false_positive", reason

    # 3. Needs Review (Asymmetric fallback): any other case, e.g. conflict, uncertainty, or partial findings
    reasons = []
    if reach_decision == "pass":
        reasons.append("reachable path found")
    elif reach_decision == "fail":
        reasons.append("path seems unreachable")
        
    if guard_decision == "pass":
        reasons.append("missing/weak guards")
    elif guard_decision == "fail":
        reasons.append("guards look solid")
        
    if exploit_decision == "pass":
        reasons.append("exploit trigger identified")
    elif exploit_decision == "fail":
        reasons.append("no exploit trigger")
        
    reason = "Divergent or incomplete votes: " + ", ".join(reasons)
    return "needs_review", reason
