import os
from typing import List, Dict
from src_v2.core.models import AuditPlan, CandidateRecord, VerificationResult
from src_v2.core.plan_io import load_plan
from src_v2.core.candidate_registry import load_candidates

def generate_review_queue_report(
    plan_path: str,
    registry_path: str,
    results_path: str,
    output_path: str
) -> str:
    """Generate review_queue.md for manual review targets."""
    plan = load_plan(plan_path)
    candidates = load_candidates(registry_path)
    
    # Load verification results
    results_map: Dict[str, VerificationResult] = {}
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        res = VerificationResult.model_validate_json(line)
                        results_map[res.candidate_id] = res
                    except:
                        pass

    # Filter needs_review based on manual_review queue file, and load deferred candidates
    workspace_dir = os.path.dirname(plan_path)
    queue_dir = os.path.join(workspace_dir, "queues")
    from src_v2.core.queue_store import load_queue
    manual_review_queue = load_queue(queue_dir, "manual_review")
    manual_review_set = set(manual_review_queue)
    
    review_cands = [c for c in candidates if c.candidate_id in manual_review_set]
    deferred_cands = [c for c in candidates if c.status == "deferred"]
    
    review_cands.sort(key=lambda x: x.priority, reverse=True)
    deferred_cands.sort(key=lambda x: x.priority, reverse=True)

    md = []
    md.append("# Manual Review Queue\n")
    md.append(f"**Target Repository**: `{plan.repo_path}`\n")
    
    md.append("## Summary")
    md.append(f"- **Needs Manual Review**: {len(review_cands)} candidates")
    md.append(f"- **Deferred (Budget limits, Lease Timeouts, or Scheduling constraints)**: {len(deferred_cands)} candidates\n")

    # Group needs_review by Shard/Track
    md.append("## Needs Review Queue\n")
    if not review_cands:
        md.append("> [!NOTE]")
        md.append("> No candidates in this run require manual review.")
        md.append("\n")
    else:
        for idx, cand in enumerate(review_cands):
            res = results_map.get(cand.candidate_id)
            reason = res.reason if res else "No details available."
            votes = res.referee_votes if res else []
            
            md.append(f"### {idx + 1}. `{cand.symbol}` in `{cand.file}`")
            md.append(f"- **Candidate ID**: `{cand.candidate_id}`")
            md.append(f"- **Shard**: `{cand.shard_id}`")
            md.append(f"- **Language**: `{cand.lang}`")
            md.append(f"- **Tracks**: {', '.join(cand.source_tracks)}")
            md.append(f"- **Priority Score**: `{cand.priority}`")
            md.append(f"- **Line Range**: `{cand.span.start} - {cand.span.end}`\n")
            
            md.append("#### Review Rationale")
            md.append(f"> {reason}\n")
            
            if votes:
                md.append("#### Referee Breakdown")
                md.append("| Referee Lens | Decision | Reason |")
                md.append("|---|---|---|")
                for v in votes:
                    decision_str = "🔴 PASS" if v.decision == "pass" else ("🟢 FAIL" if v.decision == "fail" else "🟡 UNCERTAIN")
                    md.append(f"| {v.lens} | {decision_str} | {v.reason} |")
                md.append("\n")
                
            md.append("---")
            md.append("\n")

    # Group deferred
    md.append("## Deferred Candidates (Waiting for Next Cycles)\n")
    if not deferred_cands:
        md.append("No candidates deferred in this run.")
        md.append("\n")
    else:
        md.append("| Candidate ID | File Path | Symbol | Tracks | Priority |")
        md.append("|---|---|---|---|---|")
        for dc in deferred_cands:
            md.append(f"| `{dc.candidate_id}` | `{dc.file}` | `{dc.symbol}` | {', '.join(dc.source_tracks)} | `{dc.priority}` |")
        md.append("\n")

    report_content = "\n".join(md)
    
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    return report_content
