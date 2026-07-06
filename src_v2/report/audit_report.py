import os
from typing import List, Dict
from src_v2.core.models import AuditPlan, CandidateRecord, VerificationResult
from src_v2.core.plan_io import load_plan
from src_v2.core.candidate_registry import load_candidates

def generate_audit_report(
    plan_path: str,
    registry_path: str,
    results_path: str,
    output_path: str
) -> str:
    """Generate audit_report.md for verified vulnerabilities."""
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

    # Filter verified candidates
    verified_cands = [c for c in candidates if c.status == "verified"]
    verified_cands.sort(key=lambda x: x.priority, reverse=True)

    md = []
    md.append("# Audit Report\n")
    md.append(f"**Target Repository**: `{plan.repo_path}`")
    md.append(f"**Vulnerability Count**: {len(verified_cands)}\n")
    
    if not verified_cands:
        md.append("> [!NOTE]")
        md.append("> No verified vulnerabilities found in this audit run.")
        md.append("\n")
    else:
        md.append("## Confirmed Vulnerabilities\n")
        for idx, cand in enumerate(verified_cands):
            res = results_map.get(cand.candidate_id)
            reason = res.reason if res else "No details available."
            evidence_items = res.evidence if res else []
            
            md.append(f"### {idx + 1}. {cand.symbol} in `{cand.file}`")
            md.append(f"- **Candidate ID**: `{cand.candidate_id}`")
            md.append(f"- **Shard**: `{cand.shard_id}`")
            md.append(f"- **Language**: `{cand.lang}`")
            md.append(f"- **Tracks**: {', '.join(cand.source_tracks)}")
            md.append(f"- **Rules Triggered**: {', '.join(cand.matched_rules)}")
            md.append(f"- **Line Range**: `{cand.span.start} - {cand.span.end}`")
            md.append(f"- **Priority Score**: `{cand.priority}`\n")
            
            md.append("#### Description & Reason")
            md.append(f"{reason}\n")
            
            if evidence_items:
                md.append("#### Evidence & Analysis Paths")
                for ev in evidence_items:
                    md.append(f"- **[{ev.type}]**: {ev.value}")
                md.append("\n")
                
            md.append("---")
            md.append("\n")

    report_content = "\n".join(md)
    
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    return report_content
